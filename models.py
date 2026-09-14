"""역할별 모델표와 call() (모델표). 모델명은 이 파일에서만 관리한다.

DEV_MODE(기본 1)면 개발 모델표(무료), 0이면 운영 모델표를 쓴다. 호출부는 role만 넘기므로 전환에 코드 변경이 없다.
개발 모델표에는 is_test 가짜 프로필과 공개 뉴스만 보낸다. 실제 사용자 텍스트는 보내지 않는다 (작업 규칙 7).

모델 ID 출처
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview (2026-09-13 확인)
- Google Gemini: https://ai.google.dev/gemini-api/docs/models (2026-09-13 확인)
- OpenAI: https://developers.openai.com/api/docs/models (2026-09-13 확인)
- OpenRouter 무료: https://openrouter.ai/api/v1/models 에서 id가 :free이고 supported_parameters에 tools가 있는 모델 (2026-09-14 조회)

메시지는 langchain_core.messages 형식을 쓰고, 반환도 AIMessage(tool_calls 포함)로 통일한다.
기본 모델이 429·503·529(Anthropic 과부하)를 돌려주면 대체 모델로 1회만 전환한다.
"""
import json
import logging
import os
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import convert_to_openai_messages
from langchain_core.utils.function_calling import convert_to_openai_tool

import config  # noqa: F401  .env를 os.environ에 채운다
from agent import tracing

log = logging.getLogger("toolscout.models")

ModelTable = dict[str, dict[str, dict[str, str]]]

PROD_MODELS: ModelTable = {
    "curator": {  # 큐레이터 선별
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash"},
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
        "fallback": {"provider": "gemini", "model": "gemini-3.6-flash"},
    },
}

# 선별·게이트는 빠른 모델, 검증관·해설가는 한국어가 되는 모델. 2026-09-14 실측(한국어 JSON 요약·도구 호출)으로 배정:
# nex-n2.5-mini 0.9초·한글 0.9·도구 성공 / nex-n2.5-pro 2.3초·한글 0.9·도구 성공 / nemotron-3-super 7초·한글 0.9·도구 성공
# gemma-4-31b·26b는 무료 공급자(Google AI Studio) 429가 반복돼 뺐다
# OpenRouter 무료 모델은 크레딧이 없으면 하루 50회라, 호출이 많은 검증관·해설가는 Gemini 무료 티어를 기본으로 둔다
# (2026-09-14 사용자 결정. 한도 출처: https://openrouter.ai/docs/api/reference/limits)
DEV_MODELS: ModelTable = {
    "curator": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-mini:free"},
    },
    "verifier": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-pro:free"},
    },
    "explainer": {
        "primary": {"provider": "gemini", "model": "gemini-3.6-flash"},
        "fallback": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-pro:free"},
    },
    "gate": {
        "primary": {"provider": "openrouter", "model": "nex-agi/nex-n2.5-mini:free"},
        "fallback": {"provider": "gemini", "model": "gemini-3.6-flash"},
    },
}

FALLBACK_STATUS = {429, 503, 529}  # 529는 Anthropic 과부하
MAX_TOKENS = 4096
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class ProviderError(Exception):
    """HTTP 200이지만 본문이 오류인 응답. status_code가 있으면 대체 전환 판단에 쓴다."""

    def __init__(self, message: str, status_code: Any = None):
        super().__init__(message)
        self.status_code = status_code if isinstance(status_code, int) else None


def dev_mode() -> bool:
    """DEV_MODE가 0이 아니면 개발 모드다. 값이 없으면 1로 본다."""
    return os.environ.get("DEV_MODE", "1").strip() != "0"


def active_models() -> ModelTable:
    return DEV_MODELS if dev_mode() else PROD_MODELS


def call(role: str, messages: list[BaseMessage], tools: list[Any] | None = None) -> AIMessage:
    """역할에 맞는 모델을 부른다. 429·503·529면 대체 모델로 1회 전환한다."""
    table = active_models()[role]
    openai_tools = [convert_to_openai_tool(t) for t in tools] if tools else None
    try:
        return _call_one(role, "primary", table["primary"], messages, openai_tools)
    except Exception as exc:
        status = status_code(exc)
        if status not in FALLBACK_STATUS:
            raise
        log.warning("%s 기본 모델 %s 응답 %s, 대체 모델로 전환", role, table["primary"]["model"], status)
        return _call_one(role, "fallback", table["fallback"], messages, openai_tools)


def status_code(exc: Exception) -> int | None:
    """SDK마다 다른 에러 객체에서 HTTP 상태 코드를 꺼낸다."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def _call_one(role: str, slot: str, spec: dict[str, str], messages: list[BaseMessage], tools) -> AIMessage:
    adapter = PROVIDERS[spec["provider"]]
    with tracing.span(f"llm:{role}:{slot}", kind="generation", model=spec["model"],
                      input=_summary(messages), metadata={"provider": spec["provider"], "tools": len(tools or [])}) as span:
        result = adapter(spec["model"], messages, tools)
        usage = result.usage_metadata or {}
        span.update(output={"text": result.text, "tool_calls": result.tool_calls},
                    usage_details={"input": usage.get("input_tokens", 0), "output": usage.get("output_tokens", 0)})
        result.response_metadata.update(role=role, slot=slot, trace_id=span.trace_id)
        return result


def _summary(messages: list[BaseMessage]) -> list[dict]:
    return [{"type": m.type, "content": m.text, "tool_calls": getattr(m, "tool_calls", None) or None} for m in messages]


def _split_system(messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    system = "\n\n".join(m.text for m in messages if isinstance(m, SystemMessage))
    return system, [m for m in messages if not isinstance(m, SystemMessage)]


def _usage(input_tokens: int | None, output_tokens: int | None) -> dict[str, int]:
    i, o = input_tokens or 0, output_tokens or 0
    return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}


# Anthropic ---------------------------------------------------------------

def _anthropic_client():
    import anthropic

    return anthropic.Anthropic(max_retries=0)  # 재시도는 call()의 대체 전환이 맡는다


def _anthropic(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    system, conversation = _split_system(messages)
    payload: list[dict] = []
    for m in conversation:
        if isinstance(m, HumanMessage):
            payload.append({"role": "user", "content": m.text})
        elif isinstance(m, AIMessage):
            blocks = list(m.additional_kwargs.get("anthropic_thinking", []))
            if m.text:
                blocks.append({"type": "text", "text": m.text})
            blocks += [{"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]} for tc in m.tool_calls]
            payload.append({"role": "assistant", "content": blocks})
        elif isinstance(m, ToolMessage):
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.text}
            if payload and payload[-1]["role"] == "user" and isinstance(payload[-1]["content"], list):
                payload[-1]["content"].append(block)  # 연속 도구 결과는 한 user 메시지로 묶는다
            else:
                payload.append({"role": "user", "content": [block]})
    kwargs: dict[str, Any] = {"model": model, "max_tokens": MAX_TOKENS, "messages": payload}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                            "input_schema": t["function"].get("parameters", {"type": "object"})} for t in tools]
    client = _anthropic_client()  # 변수에 잡아 둬야 요청 전에 클라이언트가 닫히지 않는다
    response = client.messages.create(**kwargs)
    blocks = response.content
    return AIMessage(
        content="".join(b.text for b in blocks if b.type == "text"),
        tool_calls=[{"name": b.name, "args": b.input, "id": b.id, "type": "tool_call"} for b in blocks if b.type == "tool_use"],
        additional_kwargs={"anthropic_thinking": [b.model_dump(exclude_none=True) for b in blocks
                                                  if b.type in ("thinking", "redacted_thinking")]},
        usage_metadata=_usage(response.usage.input_tokens, response.usage.output_tokens),
        response_metadata={"provider": "anthropic", "model": model, "stop_reason": response.stop_reason},
    )


# Gemini ------------------------------------------------------------------

def _gemini_client():
    from google import genai

    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def _gemini(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    from google.genai import types

    system, conversation = _split_system(messages)
    contents: list[types.Content] = []
    for m in conversation:
        if isinstance(m, HumanMessage):
            contents.append(types.Content(role="user", parts=[types.Part(text=m.text)]))
        elif isinstance(m, AIMessage):
            parts = m.additional_kwargs.get("gemini_parts")  # thought_signature 보존용 원본
            if not parts:
                parts = ([types.Part(text=m.text)] if m.text else []) + [
                    types.Part(function_call=types.FunctionCall(name=tc["name"], args=tc["args"], id=tc["id"]))
                    for tc in m.tool_calls]
            contents.append(types.Content(role="model", parts=parts))
        elif isinstance(m, ToolMessage):
            part = types.Part(function_response=types.FunctionResponse(
                name=m.name or "tool", response={"result": m.text}, id=m.tool_call_id))
            last = contents[-1] if contents else None
            if last is not None and last.role == "user" and last.parts and last.parts[0].function_response:
                last.parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    config = types.GenerateContentConfig(
        system_instruction=system or None,
        max_output_tokens=MAX_TOKENS,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            name=t["function"]["name"], description=t["function"].get("description", ""),
            parameters_json_schema=t["function"].get("parameters")) for t in tools])] if tools else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    client = _gemini_client()  # 변수에 잡아 둬야 요청 전에 클라이언트가 닫히지 않는다
    response = client.models.generate_content(model=model, contents=contents, config=config)
    candidate = response.candidates[0] if response.candidates else None
    parts = list(candidate.content.parts or []) if candidate and candidate.content else []
    calls = [p.function_call for p in parts if p.function_call]
    usage = response.usage_metadata
    return AIMessage(
        content="".join(p.text for p in parts if p.text and not p.thought),
        tool_calls=[{"name": c.name, "args": dict(c.args or {}), "id": c.id or f"call_{i}", "type": "tool_call"}
                    for i, c in enumerate(calls)],
        additional_kwargs={"gemini_parts": parts},
        usage_metadata=_usage(usage.prompt_token_count if usage else 0, usage.candidates_token_count if usage else 0),
        response_metadata={"provider": "gemini", "model": model,
                           "finish_reason": str(candidate.finish_reason) if candidate else None},
    )


# OpenAI 호환 (OpenAI, OpenRouter). httpx로 직접 호출해 새 라이브러리를 늘리지 않는다 ------

def _http_client() -> httpx.Client:
    return httpx.Client(timeout=120)


def _openai(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    return _openai_compatible("openai", OPENAI_URL, "OPENAI_API_KEY", {"max_completion_tokens": MAX_TOKENS},
                              model, messages, tools)


def _openrouter(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    return _openai_compatible("openrouter", OPENROUTER_URL, "OPENROUTER_API_KEY", {"max_tokens": MAX_TOKENS},
                              model, messages, tools)


def _openai_compatible(provider: str, url: str, key_env: str, limits: dict, model: str,
                       messages: list[BaseMessage], tools) -> AIMessage:
    body: dict[str, Any] = {"model": model, "messages": convert_to_openai_messages(messages), **limits}
    if tools:
        body["tools"] = tools
    headers = {"Authorization": f"Bearer {os.environ.get(key_env, '')}"}
    with _http_client() as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
    data = response.json()
    if not data.get("choices"):  # OpenRouter는 상위 공급자 오류를 200 본문의 error로 돌려줄 때가 있다
        error = data.get("error") or {}
        raise ProviderError(f"{provider} 오류 응답: {str(error.get('message', ''))[:200]}", error.get("code"))
    message = data["choices"][0]["message"]
    usage = data.get("usage") or {}
    return AIMessage(
        content=message.get("content") or "",
        tool_calls=[{"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"] or "{}"),
                     "id": tc["id"], "type": "tool_call"} for tc in message.get("tool_calls") or []],
        usage_metadata=_usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
        response_metadata={"provider": provider, "model": model, "finish_reason": data["choices"][0].get("finish_reason")},
    )


PROVIDERS: dict[str, Callable[..., AIMessage]] = {
    "anthropic": _anthropic, "gemini": _gemini, "openai": _openai, "openrouter": _openrouter,
}
