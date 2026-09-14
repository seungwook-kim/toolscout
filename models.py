"""역할별 모델표와 call() (모델표). 모델명은 이 파일에서만 관리한다. 공급자별 호출은 providers.py.

DEV_MODE(기본 1)면 개발 모델표(무료), 0이면 운영 모델표를 쓴다. 호출부는 role만 넘기므로 전환에 코드 변경이 없다.
개발 모델표에는 is_test 가짜 프로필과 공개 뉴스만 보낸다. 실제 사용자 텍스트는 보내지 않는다 (작업 규칙 7).

모델 ID 출처
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview (2026-09-13 확인)
- Google Gemini: https://ai.google.dev/gemini-api/docs/models (2026-09-13 확인)
- OpenAI: https://developers.openai.com/api/docs/models (2026-09-13 확인)
- OpenRouter 무료: https://openrouter.ai/api/v1/models 에서 id가 :free이고 supported_parameters에 tools가 있는 모델 (2026-09-14 조회)

메시지는 langchain_core.messages 형식을 쓰고, 반환도 AIMessage(tool_calls 포함)로 통일한다.
기본 모델이 429·503·529(Anthropic 과부하)를 돌려주면 대체 모델로 1회만 전환한다.
사고·추론 토큰도 출력 한도를 쓰므로 표에서 thinking(Gemini)·reasoning(OpenRouter)을 낮춰 둔다.
사고 수준 출처: https://ai.google.dev/gemini-api/docs/thinking, https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
"""
import logging
import os
import threading
import time
from typing import Any

import httpx
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

import config  # noqa: F401  .env를 os.environ에 채운다
from agent import tracing
from providers import OPTIONS, PROVIDERS

log = logging.getLogger("toolscout.models")

ModelTable = dict[str, dict[str, dict[str, str]]]

PROD_MODELS: ModelTable = {
    "curator": {  # 큐레이터 선별
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
        "fallback": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    },
    "verifier": {  # 검증관
        "primary": {"provider": "anthropic", "model": "claude-opus-5"},
        "fallback": {"provider": "anthropic", "model": "claude-sonnet-5"},
    },
    "explainer": {  # 해설가
        "primary": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "fallback": {"provider": "openai", "model": "gpt-5.6-terra"},
    },
    "gate": {  # 게이트
        "primary": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        "fallback": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
    },
}

# 선별·게이트는 빠른 모델, 검증관·해설가는 한국어가 되는 모델. 2026-09-14 실측(한국어 JSON 요약·도구 호출)으로 배정:
# nex-n2.5-mini 0.9초·한글 0.9·도구 성공 / nex-n2.5-pro 2.3초·한글 0.9·도구 성공 (둘 다 추론 필수 아님, effort none 지원)
# gemma-4-31b·26b는 무료 공급자(Google AI Studio) 429가 반복돼 뺐다
# OpenRouter 무료는 크레딧이 없으면 하루 50회라 호출이 많은 검증관·해설가는 Gemini 무료 티어를 기본으로 둔다
# (2026-09-14 사용자 결정. 한도 출처: https://openrouter.ai/docs/api/reference/limits)
DEV_MODELS: ModelTable = {
    "curator": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-mini:free", "reasoning": "none"},
    },
    "verifier": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "low"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-pro:free", "reasoning": "none"},
    },
    "explainer": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "low"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-pro:free", "reasoning": "none"},
    },
    "gate": {
        "primary": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-mini:free", "reasoning": "none"},
        "fallback": {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
    },
}

FALLBACK_STATUS = {429, 503, 529}  # 529는 Anthropic 과부하
# 개발 모드 무료 등급 호출 간격(초). OpenRouter 무료는 분당 20회
FREE_TIER_MIN_INTERVAL = {"gemini": 4.0, "openrouter": 3.5}
_last_call: dict[str, float] = {}
_throttle_lock = threading.Lock()


def dev_mode() -> bool:
    """DEV_MODE가 0이 아니면 개발 모드다. 값이 없으면 1로 본다."""
    return os.environ.get("DEV_MODE", "1").strip() != "0"


def active_models() -> ModelTable:
    return DEV_MODELS if dev_mode() else PROD_MODELS


def call(role: str, messages: list[BaseMessage], tools: list[Any] | None = None, *,
         temperature: float | None = None) -> AIMessage:
    """역할에 맞는 모델을 부른다. 429·503·529면 대체 모델로 1회 전환한다.

    temperature는 받는 공급자(Gemini, OpenRouter)에만 넘긴다. Anthropic SDK 1.5 create에는 인자가 없다.
    """
    table = active_models()[role]
    openai_tools = [convert_to_openai_tool(t) for t in tools] if tools else None
    try:
        return _call_one(role, "primary", table["primary"], messages, openai_tools, temperature)
    except Exception as exc:
        status = status_code(exc)
        if status not in FALLBACK_STATUS:
            raise
        log.warning("%s 기본 모델 %s 응답 %s, 대체 모델로 전환", role, table["primary"]["model"], status)
        return _call_one(role, "fallback", table["fallback"], messages, openai_tools, temperature)


def status_code(exc: Exception) -> int | None:
    """SDK마다 다른 에러 객체에서 HTTP 상태 코드를 꺼낸다."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _options(spec: dict[str, str], temperature: float | None) -> dict[str, Any]:
    """표의 thinking·reasoning과 호출의 temperature 중 그 공급자가 받는 것만 고른다."""
    wanted: dict[str, Any] = {k: v for k, v in spec.items() if k not in ("provider", "model")}
    if temperature is not None:
        wanted["temperature"] = temperature
    return {k: v for k, v in wanted.items() if k in OPTIONS.get(spec["provider"], ())}


def _throttle(provider: str) -> None:
    """개발 모드 무료 등급의 분당 제한을 넘지 않게 같은 공급자 호출 사이에 간격을 둔다."""
    interval = FREE_TIER_MIN_INTERVAL.get(provider, 0.0) if dev_mode() else 0.0
    if interval <= 0:
        return
    with _throttle_lock:
        wait = _last_call.get(provider, 0.0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[provider] = time.monotonic()


def _call_one(role: str, slot: str, spec: dict[str, str], messages: list[BaseMessage], tools,
              temperature: float | None = None) -> AIMessage:
    adapter = PROVIDERS[spec["provider"]]
    options = _options(spec, temperature)
    with tracing.span(f"llm:{role}:{slot}", kind="generation", model=spec["model"], model_parameters=options or None,
                      input=_summary(messages), metadata={"provider": spec["provider"], "tools": len(tools or [])}) as span:
        _throttle(spec["provider"])
        result = adapter(spec["model"], messages, tools, **options)
        usage = result.usage_metadata or {}
        span.update(output={"text": result.text, "tool_calls": result.tool_calls},
                    usage_details={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)})
        result.response_metadata.update(role=role, slot=slot, trace_id=span.trace_id)
        return result


def _summary(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "content": m.text, "tool_calls": getattr(m, "tool_calls", None) or None} for m in messages]
