"""역할별 모델표와 call() (모델표). 모델명은 이 파일에서만 관리한다. 공급자별 호출은 providers.py.

DEV_MODE(기본 1)면 개발 모델표(Claude 구독만, 2026-10-05부터), 0이면 운영 모델표를 쓴다. 호출부는 role만 넘기므로 전환에 코드 변경이 없다.
개발 모델표에는 is_test 가짜 프로필과 공개 뉴스만 보낸다. 실제 사용자 텍스트는 보내지 않는다 (작업 규칙 7).

모델 ID 출처
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview (2026-09-13 확인)
- Google Gemini: https://ai.google.dev/gemini-api/docs/models (2026-09-13 확인)
- OpenAI: https://developers.openai.com/api/docs/models (2026-09-13 확인)
- OpenRouter 무료: https://openrouter.ai/api/v1/models 에서 id가 :free이고 supported_parameters에 tools가 있는 모델 (2026-09-14 조회)
- Groq 무료: https://console.groq.com/docs/tool-use 도구 호출 지원 목록과 https://console.groq.com/docs/rate-limits (2026-09-14 확인)
- Ollama 로컬: https://ollama.com/library, VRAM·도구 호출·한글 실측은 docs/local-model.md (2026-09-14)

메시지는 langchain_core.messages 형식을 쓰고, 반환도 AIMessage(tool_calls 포함)로 통일한다.
표의 각 역할은 제공자 순서 목록이다. 503·529(Anthropic 과부하)·연결 실패·타임아웃·키 없음이면 다음 제공자로 넘어간다.
429는 60초 기다렸다가 같은 제공자에 1회 더 보내고, 그래도 429면 다음으로 넘어간다. 도구가 필요한 호출은 도구를 못 쓰는
모델(tools False)을 건너뛴다. 끝까지 실패하거나 전환 대상이 아닌 오류면 ModelUnavailable을 낸다.
사고·추론 토큰도 출력 한도를 쓰므로 표에서 thinking(Gemini)·reasoning(OpenRouter·Groq·Ollama)을 낮춰 둔다.
사고 수준 출처: https://ai.google.dev/gemini-api/docs/thinking, https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
"""
import logging
import os
import threading
import time
from collections import Counter
from typing import Any

import httpx
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

import config  # noqa: F401  .env를 os.environ에 채운다
from agent import tracing
from providers import OPTIONS, PROVIDERS, MissingKey

log = logging.getLogger("toolscout.models")

ModelTable = dict[str, list[dict[str, Any]]]

PROD_MODELS: ModelTable = {
    "curator": [  # 큐레이터 선별
        {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
        {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    ],
    "verifier": [  # 검증관
        {"provider": "anthropic", "model": "claude-opus-5"},
        {"provider": "anthropic", "model": "claude-sonnet-5"},
    ],
    "explainer": [  # 해설가
        {"provider": "anthropic", "model": "claude-sonnet-5"},
        {"provider": "openai", "model": "gpt-5.6-terra"},
    ],
    "gate": [  # 게이트
        {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
        {"provider": "gemini", "model": "gemini-3.6-flash", "thinking": "minimal"},
    ],
}

# 개발 모드는 Claude 구독만 쓴다 (2026-10-05 사용자 결정 "올라마 끄고 다 로컬에 도구모델 기반으로", 구독이 실패하면 "구독만, 실패하면 건너뜀").
# 역할마다 같은 구독 모델을 두 칸 둔다. 503(시간 초과·CLI 실패)이면 한 번 더 부르고, 529(한도·로그인)면 claude_cli가 30분 동안 CLI를
# 띄우지 않아 두 번째 칸도 바로 529 → ModelUnavailable로 호출부가 그 묶음·카드를 건너뛴다. 무료 원격(groq·gemini·openrouter)은 부르지 않는다
# 아래 로컬·무료 모델 설명은 표에 있던 때(Ollama 2026-09-14~10-04, 무료 원격 ~10-05)의 기록이다
# - 로컬 모델은 VRAM 8~9GB 안에서 가장 큰 모델을 실측으로 골랐다: gemma3:12b Q4_K_M, num_ctx 8192에서 8.96GiB (docs/local-model.md)
#   gemma3:12b는 도구 호출을 지원하지 않아(tools False) 큐레이터·게이트는 첫 제공자, 해설가는 groq 다음 대체로 둔다.
#   해설가는 모델에 도구를 주지 않으므로 대체로 쓸 수 있고, 도구가 필요한 호출이면 건너뛴다 (2026-09-15 사용자 결정)
#   num_ctx 8192는 서버 환경변수 OLLAMA_CONTEXT_LENGTH, 온도 0은 호출에서. 사고 모델이 아니라 reasoning을 넘기지 않는다
# - Groq는 도구 호출 지원 목록에서 한국어가 되는 qwen3를 해설가·검증관에, 가벼운 gpt-oss-20b를 선별·게이트에 둔다.
#   분당 토큰 8K가 모델별이라 역할을 두 모델로 나눴다. 2026-09-14 목록 API·실제 도구 호출·JSON 응답으로 확정
#   (tests/models/check_groq.py, 하루 1,000회·분당 8,000토큰. llama-3.3-70b-versatile은 이 계정에서 404)
# - gemma-4-31b·26b는 무료 공급자(Google AI Studio) 429가 반복돼 뺐다 / OpenRouter 무료는 크레딧이 없으면 하루 50회
#
# 배포용 후보 (2026-09-21 실측, 아직 표에 넣지 않았다. 로컬을 못 쓰는 곳에 올릴 때 ollama 자리를 이걸로 바꾼다)
#   openrouter openai/gpt-oss-20b: 선별 20건 5.0초(로컬 gemma3:12b 18.2초의 3.6배), JSON 규격 맞음,
#   도구 호출 지원(로컬 모델의 가장 큰 제약이 풀린다), 한국어 요약 자연스러움. 입력 $0.030·출력 $0.130 per 1M,
#   혼자 쓰면 하루 약 $0.005. reasoning은 반드시 low로 준다. none은 400(Reasoning is mandatory for this endpoint),
#   지정하지 않으면 사고 토큰이 붙어 출력이 약 3배가 된다
#   해설가·검증관 자리는 openrouter qwen/qwen3.8-27b(입력 $0.200·출력 $2.500 per 1M)를 같이 본다
# Claude 구독 (2026-09-28 사용자 결정 "지금은 너 자체의 구독 시스템으로 돌려라"). 개발자 본인이 로그인한 Claude Code CLI를
# claude_cli.py가 `claude -p`로 부른다. API 과금 없음. 도구 호출도 구독으로(도구 목록을 글로 알려 주고 JSON 약속으로 받는다).
# 모델 ID는 Claude Code가 받는 이름(2026-09-28 Claude Code 2.1.283 기준): 해설가·검증관 Sonnet 5, 큐레이터·게이트 Haiku 4.5.
# 한도·로그인 문제(529)나 실패(503)의 처리는 위 개발 모드 설명을 따른다. 구독은 개인 사용 범위이고, 배포할 때는 OpenRouter 키를
# 넣어 운영 모드로 간다(2026-09-28 사용자 "배포할 때는 오픈라우터 키 넣을 거니까, 지금 로컬은 구독 LLM")
CC_SONNET = {"provider": "claude_code", "model": "claude-sonnet-5"}  # 도구 호출은 글 약속으로(claude_cli.py)
# 큐레이터·게이트는 형식이 정해진 판정이라 생각을 끈다(9/29 선별 19번이 생각 때문에 31분, 끄고 같은 요청이 100초 → 6초).
# 해설가·검증관은 문장 품질·위험 판단이라 켜 둔다(9/29 해설가 21번 8.6분)
CC_HAIKU = {"provider": "claude_code", "model": "claude-haiku-4-5-20251001", "thinking": False}
# 표에 Ollama가 없으니 06:55 예열(warm_local)도 Ollama를 부르지 않는다. 표에서 뺀 Ollama·Groq 정의와 providers 변환은 다시 넣을 때를 위해 둔다
LOCAL_JSON_MODEL = {"provider": "ollama", "model": "gemma3:12b", "tools": False}
GROQ_FAST = {"provider": "groq", "model": "openai/gpt-oss-20b", "reasoning": "low"}
GROQ_KOREAN = {"provider": "groq", "model": "qwen/qwen3.8-27b", "reasoning": "none"}
DEV_MODELS: ModelTable = {
    "curator": [CC_HAIKU, CC_HAIKU],
    "verifier": [CC_SONNET, CC_SONNET],
    "explainer": [CC_SONNET, CC_SONNET],
    "gate": [CC_HAIKU, CC_HAIKU],
}

FALLBACK_STATUS = {429, 503, 529}  # 529는 Anthropic 과부하
SLOT_NAMES = ["primary", "fallback", "fallback2", "fallback3", "fallback4"]  # 구독 모델을 앞에 넣어 체인이 5칸까지
# 429는 60초 기다렸다가 같은 제공자에 1회 더 보내고, 그래도 429면 다음 제공자로 (2026-09-15 사용자 결정)
RATE_LIMIT_WAIT_SECONDS = 60
_sleep = time.sleep  # 검수에서 기다리지 않게 바꿔 끼운다
# 개발 모드 무료 등급 호출 간격(초). OpenRouter 무료는 분당 20회.
# Groq 무료는 분당 30회지만 분당 토큰 8,000이 먼저 막힌다. 해설가 1회가 용어집·원문 포함 약 3~4K 토큰이라 분당 2회로 둔다
FREE_TIER_MIN_INTERVAL = {"gemini": 4.0, "openrouter": 3.5, "groq": 30.0}
_last_call: dict[str, float] = {}
_throttle_lock = threading.Lock()
# 이 프로세스에서 성공한 호출 수 (제공자:모델), 전환 사유, 429 받은 횟수(제공자별). 하루 실행 보고에 쓴다
PROVIDER_CALLS: Counter = Counter()
FAILOVERS: Counter = Counter()
RATE_LIMITS: Counter = Counter()


class ModelUnavailable(Exception):
    """역할의 제공자 목록을 끝까지 시도해도 답을 못 받았다. 파이프라인은 그 사용자·카드만 건너뛴다."""

    def __init__(self, role: str, attempts: list[str]):
        super().__init__(f"{role} 모델 장애: {'; '.join(attempts)}")
        self.role, self.attempts = role, attempts


def dev_mode() -> bool:
    """DEV_MODE가 0이 아니면 개발 모드다. 값이 없으면 1로 본다."""
    return os.environ.get("DEV_MODE", "1").strip() != "0"


# 역할표 밖 단일 모델 (2026-09-23 사용자 결정). 운영 모드용(개발 모드는 아래 DEV_SINGLE_MODEL_ROLES), 다른 모델로 대체하지 않는다(끝내 실패하면 ModelUnavailable → 호출부가 건너뜀)
# - same_story: 같은 소식 묶기·큰 소식 묶기(agent/same_story.py). 유료 OpenRouter 키, 사용자가 정한 모델이다.
#   9/23 시험 7세트 중 5세트 정답, 2세트에서 다른 소식을 뺐다. 다른 OpenRouter 모델로 바꾸거나 시험하지 않는다 (사용자 결정)
#   출처: https://openrouter.ai/api/v1/models (2026-09-23 조회, 입력 $0.15·출력 $0.60 per 1M)
# 9/24 07:14 이 모델이 한 번 시간 초과로 실패해 그날 큰 소식이 빠졌다. 타임아웃·503이면 같은 모델로 한 번 더 부른다 (2026-09-25)
_SAME_STORY = {"provider": "openrouter", "model": "openai/gpt-4o-mini"}
SINGLE_MODEL_ROLES: ModelTable = {
    "same_story": [_SAME_STORY, _SAME_STORY],
}
# 뉴스 중요도 점수(agent/importance.py): Jev. 사용자가 jevtypesafeai.com에서 산 키(JEV_API_KEY)라 그 사이트 주소로 부른다.
# TypeSafe 공식 API(api.typesafe.ai)에서는 이 키가 401이다. 이 사이트는 "TypeSafe AI와 관계없는 독립 플랫폼"이라고 밝힌다.
# 9/23 실측: 호출 1회 약 460토큰 $0.0002, 골든셋 32건 순위상관 0.94 (qwen 0.98·gemma 0.82·gpt-4o-mini 0.82)
JEV = {"url": "https://jevtypesafeai.com/api/v1/decide", "key_env": "JEV_API_KEY", "model": "jev-1.13.0"}
# 개발 모드에서는 역할표 밖 호출도 구독으로 (2026-10-05 사용자 결정 "전부 구독으로"). 운영 모드는 위 same_story·Jev 그대로
# - same_story: 다른 소식을 잘못 묶으면 카드가 빠져(gemma3는 5건 중 3건) 판단 품질이 중요하고, 하루 2번 남짓이라 Sonnet 5
# - importance: Jev 자리(Jev는 10/1~10/5 매일 연결 실패). 선별 통과 뉴스 20건 묶음마다 1~5점, 형식이 정해진 판정이라 Haiku 4.5(생각 끔)
DEV_SINGLE_MODEL_ROLES: ModelTable = {
    "same_story": [CC_SONNET, CC_SONNET],
    "importance": [CC_HAIKU, CC_HAIKU],
}


def active_models() -> ModelTable:
    if dev_mode():
        return {**DEV_MODELS, **DEV_SINGLE_MODEL_ROLES}
    return {**PROD_MODELS, **SINGLE_MODEL_ROLES}


def call(role: str, messages: list[BaseMessage], tools: list[Any] | None = None, *,
         temperature: float | None = None) -> AIMessage:
    """역할에 맞는 모델을 순서대로 부른다. 전환 대상 오류면 다음 제공자로 한 번씩 넘어간다.

    - 429는 60초 기다렸다가 같은 제공자에 1회 더 보내고, 그래도 429면 다음 제공자로
    - 도구가 필요한 호출에서 도구 호출을 못 하는 모델(tools False)은 건너뛴다
    temperature는 받는 공급자에만 넘긴다. Anthropic SDK 1.5 create에는 인자가 없다.
    """
    chain = active_models()[role]
    openai_tools = [convert_to_openai_tool(t) for t in tools] if tools else None
    attempts: list[str] = []
    last_exc: Exception | None = None
    for index, spec in enumerate(chain):
        if openai_tools and spec.get("tools") is False:
            attempts.append(f"{spec['provider']} 도구 호출 미지원이라 건너뜀")
            continue
        for attempt in (1, 2):
            try:
                result = _call_one(role, SLOT_NAMES[index], spec, messages, openai_tools, temperature)
                PROVIDER_CALLS[f"{spec['provider']}:{spec['model']}"] += 1
                return result
            except Exception as exc:
                last_exc = exc
                reason = failover_reason(exc)
                if reason == "429":
                    RATE_LIMITS[spec["provider"]] += 1
                    if attempt == 1:
                        log.warning("%s %s 429, %d초 뒤 같은 제공자에 한 번 더", role, spec["provider"], RATE_LIMIT_WAIT_SECONDS)
                        _sleep(RATE_LIMIT_WAIT_SECONDS)
                        continue
                attempts.append(f"{spec['provider']} {reason or type(exc).__name__}")
                if reason is None:
                    raise ModelUnavailable(role, attempts) from exc
                FAILOVERS[f"{spec['provider']}:{reason}"] += 1
                log.warning("%s %s %s, 다음 제공자로 전환", role, spec["provider"], reason)
                break
    raise ModelUnavailable(role, attempts) from last_exc


def warm_local() -> list[dict]:
    """06:55 예열. 현재 모델표의 로컬(ollama) 모델마다 짧은 프롬프트를 1회 보내 VRAM에 올려 둔다 (2026-09-15 사용자 결정).

    반환: [{model, ok, seconds, error?}]. 첫 호출이라 제한 시간은 providers의 로컬 첫 호출 값(90초)을 따른다.
    """
    from langchain_core.messages import HumanMessage

    results, seen = [], set()
    for role, chain in active_models().items():
        for index, spec in enumerate(chain):
            if spec["provider"] != "ollama" or spec["model"] in seen:
                continue
            seen.add(spec["model"])
            started = time.perf_counter()
            try:
                _call_one("warmup", SLOT_NAMES[index], spec, [HumanMessage("OK라고만 답해")], None, 0)
                results.append({"model": spec["model"], "ok": True, "seconds": round(time.perf_counter() - started, 1)})
            except Exception as exc:  # 예열 실패는 실행을 막지 않는다. 첫 호출이 90초 제한으로 다시 올린다
                results.append({"model": spec["model"], "ok": False, "seconds": round(time.perf_counter() - started, 1),
                                "error": f"{type(exc).__name__}"})
    return results


def failover_reason(exc: Exception) -> str | None:
    """다음 제공자로 넘어갈 오류면 짧은 사유, 아니면 None."""
    status = status_code(exc)
    if status in FALLBACK_STATUS:
        return str(status)
    if isinstance(exc, MissingKey):
        return "키 없음"
    if isinstance(exc, httpx.TimeoutException):
        return "타임아웃"
    if isinstance(exc, httpx.TransportError):
        return "연결 실패"
    return None


def status_code(exc: Exception) -> int | None:
    """SDK마다 다른 에러 객체에서 HTTP 상태 코드를 꺼낸다."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _options(spec: dict[str, Any], temperature: float | None) -> dict[str, Any]:
    """표의 thinking·reasoning과 호출의 temperature 중 그 공급자가 받는 것만 고른다."""
    wanted: dict[str, Any] = {k: v for k, v in spec.items() if k not in ("provider", "model", "tools")}
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


def _call_one(role: str, slot: str, spec: dict[str, Any], messages: list[BaseMessage], tools,
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
        result.response_metadata.update(role=role, slot=slot, trace_id=span.trace_id,
                                        provider=spec["provider"], model=spec["model"])
        return result


def _summary(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "content": m.text, "tool_calls": getattr(m, "tool_calls", None) or None} for m in messages]
