"""공급자별 모델 호출 (Anthropic, Gemini, OpenAI 호환). 모델명과 역할 배정은 models.py에만 둔다.

모두 langchain_core 메시지를 받아 AIMessage(tool_calls 포함)로 돌려준다.
선택 옵션: temperature(Gemini·OpenRouter), thinking(Gemini thinking_level), reasoning(OpenRouter reasoning.effort).
"""
import json
import os
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import convert_to_openai_messages

import config  # noqa: F401  .env를 os.environ에 채운다

MAX_TOKENS = 4096
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class ProviderError(Exception):
    """HTTP 200이지만 본문이 오류인 응답. status_code가 있으면 대체 전환 판단에 쓴다."""

    def __init__(self, message: str, status_code: Any = None):
        super().__init__(message)
        self.status_code = status_code if isinstance(status_code, int) else None


def _split_system(messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
    system = "\n\n".join(m.text for m in messages if isinstance(m, SystemMessage))
    return system, [m for m in messages if not isinstance(m, SystemMessage)]


def _usage(input_tokens: int | None, output_tokens: int | None) -> dict[str, int]:
    i, o = input_tokens or 0, output_tokens or 0
    return {"input_tokens": i, "output_tokens": o, "total_tokens": i + o}


# Anthropic ---------------------------------------------------------------

def _anthropic_client():
    import anthropic

    return anthropic.Anthropic(max_retries=0)  # 재시도는 models.call()의 대체 전환이 맡는다


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


def _gemini(model: str, messages: list[BaseMessage], tools, temperature: float | None = None,
            thinking: str | None = None) -> AIMessage:
    """thinking: thinking_level (minimal·low·medium·high). 사고 토큰도 출력 한도에 들어가므로 낮춰 둔다."""
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
    config_ = types.GenerateContentConfig(
        system_instruction=system or None,
        max_output_tokens=MAX_TOKENS,
        temperature=temperature,
        thinking_config=types.ThinkingConfig(thinking_level=thinking) if thinking else None,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            name=t["function"]["name"], description=t["function"].get("description", ""),
            parameters_json_schema=t["function"].get("parameters")) for t in tools])] if tools else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    client = _gemini_client()  # 변수에 잡아 둬야 요청 전에 클라이언트가 닫히지 않는다
    response = client.models.generate_content(model=model, contents=contents, config=config_)
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


def _openrouter(model: str, messages: list[BaseMessage], tools, temperature: float | None = None,
                reasoning: str | None = None) -> AIMessage:
    """reasoning: reasoning.effort (none·low·medium·high). 필수 추론 모델은 none을 거부한다."""
    extra: dict[str, Any] = {"max_tokens": MAX_TOKENS}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning:
        extra["reasoning"] = {"effort": reasoning}
    return _openai_compatible("openrouter", OPENROUTER_URL, "OPENROUTER_API_KEY", extra, model, messages, tools)


def _openai_compatible(provider: str, url: str, key_env: str, extra: dict, model: str,
                       messages: list[BaseMessage], tools) -> AIMessage:
    body: dict[str, Any] = {"model": model, "messages": convert_to_openai_messages(messages), **extra}
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
# 공급자별로 받는 선택 옵션. models._call_one이 이 목록에 있는 것만 넘긴다
OPTIONS: dict[str, tuple[str, ...]] = {"anthropic": (), "openai": (), "gemini": ("temperature", "thinking"),
                                       "openrouter": ("temperature", "reasoning")}
