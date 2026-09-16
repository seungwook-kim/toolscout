"""공급자별 모델 호출 (Anthropic, Gemini, OpenAI 호환: OpenAI·OpenRouter·Groq·Ollama, OpenCode Zen Responses API). 모델명과 역할 배정은 models.py에만.

모두 langchain_core 메시지를 받아 AIMessage(tool_calls 포함)로 돌려준다.
선택 옵션: temperature(Gemini·OpenRouter·Groq·Ollama), thinking(Gemini thinking_level),
reasoning(OpenRouter reasoning.effort, Groq·Ollama reasoning_effort).
"""
import json
import os
import time
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import convert_to_openai_messages

import config  # noqa: F401  .env를 os.environ에 채운다

MAX_TOKENS = 4096
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"  # 로컬 Ollama OpenAI 호환, 키 불필요
OPENCODE_URL = "https://opencode.ai/zen/v1/responses"  # Muse Spark는 Responses API (https://opencode.ai/docs/zen, 2026-09-16 확인)
REMOTE_TIMEOUT = 120
LOCAL_TIMEOUT = 30  # 로컬 모델이 30초 안에 답하지 않으면 타임아웃으로 다음 제공자
# 모델이 VRAM에 없을 때(프로세스 첫 호출, 또는 OLLAMA_KEEP_ALIVE 30분보다 오래 쉼)는 올리는 시간이 들어 90초 (2026-09-15 사용자 결정)
LOCAL_FIRST_TIMEOUT = 90
LOCAL_KEEP_ALIVE_SECONDS = 30 * 60
_local_last_ok: dict[str, float] = {}


def local_timeout(model: str) -> float:
    last = _local_last_ok.get(model)
    return LOCAL_TIMEOUT if last is not None and time.time() - last < LOCAL_KEEP_ALIVE_SECONDS else LOCAL_FIRST_TIMEOUT


class ProviderError(Exception):
    """HTTP 200이지만 본문이 오류인 응답. status_code가 있으면 대체 전환 판단에 쓴다."""

    def __init__(self, message: str, status_code: Any = None):
        super().__init__(message)
        self.status_code = status_code if isinstance(status_code, int) else None


class MissingKey(Exception):
    """키가 비어 있어 부르지 않은 공급자. models.call이 다음 제공자로 넘어간다. 키 이름만 담는다."""


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


# OpenAI 호환 (OpenAI, OpenRouter, Groq, Ollama). httpx로 직접 호출해 새 라이브러리를 늘리지 않는다 ------

def _http_client(timeout: float = REMOTE_TIMEOUT) -> httpx.Client:
    return httpx.Client(timeout=timeout)


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


def _groq(model: str, messages: list[BaseMessage], tools, temperature: float | None = None,
          reasoning: str | None = None) -> AIMessage:
    """reasoning: reasoning_effort (모델마다 받는 값이 다르다. 모델표에 맞는 값을 둔다)."""
    extra: dict[str, Any] = {"max_tokens": MAX_TOKENS}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning:
        extra["reasoning_effort"] = reasoning
    return _openai_compatible("groq", GROQ_URL, "GROQ_API_KEY", extra, model, messages, tools)


def _ollama(model: str, messages: list[BaseMessage], tools, temperature: float | None = None,
            reasoning: str | None = None) -> AIMessage:
    """로컬 Ollama. reasoning=none이면 사고를 끈다 (사고 모델 실측: 사고 토큰 0).

    OpenAI 호환 API는 요청의 options.num_ctx를 무시한다 (2026-09-14 실측). num_ctx 8192는 서버 환경변수
    OLLAMA_CONTEXT_LENGTH=8192로 고정한다 (docs/local-model.md).
    """
    extra: dict[str, Any] = {"max_tokens": MAX_TOKENS}
    if temperature is not None:
        extra["temperature"] = temperature
    if reasoning:
        extra["reasoning_effort"] = reasoning
    result = _openai_compatible("ollama", OLLAMA_URL, None, extra, model, messages, tools, timeout=local_timeout(model))
    _local_last_ok[model] = time.time()
    return result


def _openai_compatible(provider: str, url: str, key_env: str | None, extra: dict, model: str,
                       messages: list[BaseMessage], tools, timeout: float = REMOTE_TIMEOUT) -> AIMessage:
    body: dict[str, Any] = {"model": model, "messages": convert_to_openai_messages(messages), **extra}
    if tools:
        body["tools"] = tools
    headers = {}
    if key_env:
        if not os.environ.get(key_env):
            raise MissingKey(f"{key_env} 비어있음")
        headers["Authorization"] = f"Bearer {os.environ[key_env]}"
    with _http_client(timeout) as client:
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


def _opencode(model: str, messages: list[BaseMessage], tools) -> AIMessage:
    """OpenCode Zen Responses API. 시스템은 instructions, 대화는 input 항목(function_call·function_call_output), 도구는 평평한 function.
    응답 output의 output_text는 본문, function_call은 tool_calls로 돌린다. reasoning 항목은 다시 보내지 않는다(store false라 id 참조 불가)."""
    if not os.environ.get("OPENCODE_API_KEY"):
        raise MissingKey("OPENCODE_API_KEY 비어있음")
    system, conversation = _split_system(messages)
    items: list[dict] = []
    for m in conversation:
        if isinstance(m, HumanMessage):
            items.append({"role": "user", "content": m.text})
        elif isinstance(m, AIMessage):
            items += [{"role": "assistant", "content": m.text}] if m.text else []
            items += [{"type": "function_call", "call_id": tc["id"], "name": tc["name"], "arguments": json.dumps(tc["args"], ensure_ascii=False)}
                      for tc in m.tool_calls]
        elif isinstance(m, ToolMessage):
            items.append({"type": "function_call_output", "call_id": m.tool_call_id, "output": m.text})
    body: dict[str, Any] = {"model": model, "input": items, "max_output_tokens": MAX_TOKENS, "store": False}
    if system:
        body["instructions"] = system
    if tools:
        body["tools"] = [{"type": "function", "name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "parameters": t["function"].get("parameters", {"type": "object"})} for t in tools]
    with _http_client() as client:
        response = client.post(OPENCODE_URL, headers={"Authorization": f"Bearer {os.environ['OPENCODE_API_KEY']}"}, json=body)
    data = response.json() if "json" in response.headers.get("content-type", "") else {}
    if response.status_code >= 400 and data.get("error"):  # 오류 종류·문구를 남긴다 (무료 등급 400 MissingSessionID 등)
        raise ProviderError(f"opencode {response.status_code} {data['error'].get('type')}: {str(data['error'].get('message'))[:160]}",
                            response.status_code)
    response.raise_for_status()
    if data.get("error") or "output" not in data:
        error = data.get("error") or {}
        raise ProviderError(f"opencode 오류 응답: {str(error.get('message', ''))[:200]}", error.get("code"))
    output = data["output"] or []
    usage = data.get("usage") or {}
    return AIMessage(
        content="".join(part.get("text") or "" for item in output if item.get("type") == "message"
                        for part in item.get("content") or [] if part.get("type") == "output_text"),
        tool_calls=[{"name": i["name"], "args": json.loads(i.get("arguments") or "{}"), "id": i.get("call_id") or i.get("id"), "type": "tool_call"}
                    for i in output if i.get("type") == "function_call"],
        usage_metadata=_usage(usage.get("input_tokens"), usage.get("output_tokens")),
        response_metadata={"provider": "opencode", "model": model, "finish_reason": data.get("status")},
    )


PROVIDERS: dict[str, Callable[..., AIMessage]] = {
    "anthropic": _anthropic, "gemini": _gemini, "openai": _openai, "openrouter": _openrouter,
    "groq": _groq, "ollama": _ollama, "opencode": _opencode,
}
# 공급자별로 받는 선택 옵션. models._call_one이 이 목록에 있는 것만 넘긴다
OPTIONS: dict[str, tuple[str, ...]] = {"anthropic": (), "openai": (), "gemini": ("temperature", "thinking"),
                                       "openrouter": ("temperature", "reasoning"), "groq": ("temperature", "reasoning"),
                                       "ollama": ("temperature", "reasoning"), "opencode": ()}
