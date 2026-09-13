"""역할별 모델표와 call() (모델표). 모델명은 이 파일에서만 관리한다.

모델 ID 출처 (2026-09-13 확인)
- Anthropic: https://platform.claude.com/docs/en/about-claude/models/overview
- Google Gemini: https://ai.google.dev/gemini-api/docs/models
- OpenAI: https://developers.openai.com/api/docs/models

메시지는 langchain_core.messages 형식을 쓰고, 반환도 AIMessage(tool_calls 포함)로 통일한다.
기본 모델이 429·503을 돌려주면 대체 모델로 1회만 전환한다.
"""
import json
import logging
import os
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import convert_to_openai_messages
from langchain_core.utils.function_calling import convert_to_openai_tool

from agent import tracing

log = logging.getLogger("toolscout.models")

MODELS: dict[str, dict[str, dict[str, str]]] = {
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

FALLBACK_STATUS = {429, 503}
MAX_TOKENS = 4096
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def call(role: str, messages: list[BaseMessage], tools: list[Any] | None = None) -> AIMessage:
    """역할에 맞는 모델을 부른다. 429·503이면 대체 모델로 1회 전환한다."""
    table = MODELS[role]
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
    response = _anthropic_client().messages.create(**kwargs)
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
    response = _gemini_client().models.generate_content(model=model, contents=contents, config=config)
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


# OpenAI (httpx로 직접 호출. 새 라이브러리를 늘리지 않는다) ------------------

def _http_client() -> httpx.Client:
    return httpx.Client(timeout=120)


def _openai(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    body: dict[str, Any] = {"model": model, "messages": convert_to_openai_messages(messages),
                            "max_completion_tokens": MAX_TOKENS}
    if tools:
        body["tools"] = tools
    headers = {"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"}
    with _http_client() as client:
        response = client.post(OPENAI_URL, headers=headers, json=body)
        response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    usage = data.get("usage") or {}
    return AIMessage(
        content=message.get("content") or "",
        tool_calls=[{"name": tc["function"]["name"], "args": json.loads(tc["function"]["arguments"] or "{}"),
                     "id": tc["id"], "type": "tool_call"} for tc in message.get("tool_calls") or []],
        usage_metadata=_usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
        response_metadata={"provider": "openai", "model": model, "finish_reason": data["choices"][0].get("finish_reason")},
    )


PROVIDERS: dict[str, Callable[..., AIMessage]] = {"anthropic": _anthropic, "gemini": _gemini, "openai": _openai}
