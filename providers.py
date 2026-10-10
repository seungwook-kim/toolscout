"""공급자별 모델 호출 (Anthropic(httpx), Gemini, OpenAI 호환: OpenAI·OpenRouter·Groq·Ollama). 모델명과 역할 배정은 models.py에만 둔다.

모두 langchain_core 메시지를 받아 AIMessage(tool_calls 포함)로 돌려준다.
선택 옵션: temperature(Gemini·OpenRouter·Groq·Ollama), thinking(Gemini thinking_level),
reasoning(OpenRouter reasoning.effort, Groq·Ollama reasoning_effort), json_schema(Anthropic 구조화 출력, models.STRUCTURED_SCHEMA에서).
"""
import json
import logging
import os
import time
from typing import Any, Callable

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages import convert_to_openai_messages

import config  # noqa: F401  .env를 os.environ에 채운다

log = logging.getLogger("toolscout.providers")

MAX_TOKENS = 4096
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/v1/chat/completions"  # 로컬 Ollama OpenAI 호환, 키 불필요
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


# Anthropic (Messages API를 httpx로 직접 호출. 새 라이브러리 없음) ------------------------------------

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# 구조화 출력이 지원하지 않는 JSON 스키마 키. 값 범위·형식 검사는 어차피 agent/structured.py가 pydantic으로 다시 한다.
# pattern(정규식)은 2026-10-11 리허설에서 해설가 스키마(Evidence.evidence_url)를 "Schema is too complex"(400)로 만들었다
_SCHEMA_DROP = {"title", "default", "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "minItems", "maxItems", "format", "pattern"}


def strict_schema(node: Any) -> Any:
    """pydantic JSON 스키마를 Anthropic 구조화 출력 규칙에 맞춘다: 모든 object에 additionalProperties false, 범위 키는 뺀다."""
    if isinstance(node, list):
        return [strict_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: strict_schema(v) for k, v in node.items() if k not in _SCHEMA_DROP}
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


def anthropic_messages(messages: list[BaseMessage]) -> tuple[str, list[dict]]:
    """langchain 메시지 → (system 글, Anthropic messages). 도구 결과는 user의 tool_result 블록이고 연속이면 한 메시지로 묶는다."""
    system, conversation = _split_system(messages)
    payload: list[dict] = []
    for m in conversation:
        if isinstance(m, HumanMessage):
            payload.append({"role": "user", "content": m.text})
        elif isinstance(m, AIMessage):
            blocks: list[dict] = [{"type": "text", "text": m.text}] if m.text else []
            blocks += [{"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["args"]} for tc in m.tool_calls]
            if blocks:
                payload.append({"role": "assistant", "content": blocks})
        elif isinstance(m, ToolMessage):
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.text}
            if payload and payload[-1]["role"] == "user" and isinstance(payload[-1]["content"], list):
                payload[-1]["content"].append(block)  # 연속 도구 결과는 한 user 메시지로 묶는다
            else:
                payload.append({"role": "user", "content": [block]})
    return system, payload


def _schema_rejected(response) -> bool:
    """400 응답이 구조화 출력 스키마 거절인지. 오류 문장만 보고, 응답 전체는 로그에 쓰지 않는다."""
    try:
        message = (response.json().get("error") or {}).get("message") or ""
    except ValueError:
        return False
    return "schema" in message.lower()


def _anthropic(model: str, messages: list[BaseMessage], tools, json_schema: dict | None = None) -> AIMessage:
    """json_schema가 있고 도구가 없으면 구조화 출력(output_config.format)으로 받는다.

    강제 도구 호출(tool_choice)은 쓰지 않는다: 최신 모델(Sonnet 5.5·Opus 5.5 등)이 400으로 거절한다. 구조화 출력은 응답 글이
    스키마에 맞는 JSON으로 나오고, 지금 흐름(loop.parse_output이 글을 JSON으로 읽음)에 그대로 들어간다 (2026-10-11 Haiku 5.5 실호출 확인).
    재시도는 하지 않는다. 429·529·5xx는 models.call()의 대체 전환이 맡는다. 키와 응답 전체는 로그·오류에 넣지 않는다.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise MissingKey("ANTHROPIC_API_KEY 비어있음")
    system, payload = anthropic_messages(messages)
    body: dict[str, Any] = {"model": model, "max_tokens": MAX_TOKENS, "messages": payload}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in tools]
    elif json_schema:
        body["output_config"] = {"format": {"type": "json_schema", "schema": strict_schema(json_schema)}}
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    with _http_client(REMOTE_TIMEOUT) as client:
        response = client.post(ANTHROPIC_URL, headers=headers, json=body)
        if response.status_code == 400 and "output_config" in body and _schema_rejected(response):
            # 구조화 출력 스키마를 거절하면(400 "Schema ...") 형식 강제 없이 한 번 더 묻는다. 형식은 structured.py가 검사·재시도한다
            log.warning("Anthropic이 구조화 출력 스키마를 거절해 형식 강제 없이 다시 묻는다")
            body.pop("output_config")
            response = client.post(ANTHROPIC_URL, headers=headers, json=body)
        response.raise_for_status()
    data = response.json()
    blocks = data.get("content") or []
    usage = data.get("usage") or {}
    return AIMessage(
        content="".join(b.get("text", "") for b in blocks if b.get("type") == "text"),
        tool_calls=[{"name": b["name"], "args": b.get("input") or {}, "id": b["id"], "type": "tool_call"}
                    for b in blocks if b.get("type") == "tool_use"],
        usage_metadata=_usage(usage.get("input_tokens"), usage.get("output_tokens")),
        response_metadata={"provider": "anthropic", "model": model, "stop_reason": data.get("stop_reason")},
    )


# Gemini ------------------------------------------------------------------

def _gemini_client():
    from google import genai

    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def gemini_contents(conversation: list[BaseMessage]) -> list:
    """대화 기록 → Gemini contents.

    Gemini가 만든 도구 호출은 원본 parts(thought_signature 포함)를 그대로 보낸다. 다른 제공자가 만든 도구 호출(예: Groq가
    README를 읽은 뒤 429로 Gemini에 넘어온 경우)은 서명이 없어 Gemini 3가 400 INVALID_ARGUMENT로 거절한다(2026-09-28 07:19,
    검증관 anythingmcp). 그런 호출과 그 결과는 함수 호출 형식 대신 글로 바꿔 넘겨 내용은 그대로 보이게 한다.
    """
    from google.genai import types

    contents: list[types.Content] = []
    as_text: set[str] = set()  # 글로 바꾼 도구 호출 id
    for m in conversation:
        if isinstance(m, HumanMessage):
            contents.append(types.Content(role="user", parts=[types.Part(text=m.text)]))
        elif isinstance(m, AIMessage):
            parts = m.additional_kwargs.get("gemini_parts")  # thought_signature 보존용 원본
            if not parts:
                calls = [f"[도구 호출 {tc['name']}] {json.dumps(tc['args'], ensure_ascii=False)}" for tc in m.tool_calls]
                as_text.update(tc["id"] for tc in m.tool_calls)
                text = "\n".join(([m.text] if m.text else []) + calls)
                parts = [types.Part(text=text)] if text else []
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        elif isinstance(m, ToolMessage):
            if m.tool_call_id in as_text:
                contents.append(types.Content(role="user", parts=[types.Part(text=f"[도구 결과 {m.name or 'tool'}] {m.text}")]))
                continue
            part = types.Part(function_response=types.FunctionResponse(
                name=m.name or "tool", response={"result": m.text}, id=m.tool_call_id))
            last = contents[-1] if contents else None
            if last is not None and last.role == "user" and last.parts and last.parts[0].function_response:
                last.parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    return contents


def _gemini(model: str, messages: list[BaseMessage], tools, temperature: float | None = None,
            thinking: str | None = None) -> AIMessage:
    """thinking: thinking_level (minimal·low·medium·high). 사고 토큰도 출력 한도에 들어가므로 낮춰 둔다."""
    from google.genai import types

    system, conversation = _split_system(messages)
    contents = gemini_contents(conversation)
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


def _claude_code(model: str, messages: list[BaseMessage], tools, thinking: bool | None = None) -> AIMessage:
    import claude_cli  # Claude 구독(Claude Code CLI). 2026-09-28 사용자 결정, 자세한 규칙은 claude_cli.py

    return claude_cli.call(model, messages, tools, thinking=thinking)


PROVIDERS: dict[str, Callable[..., AIMessage]] = {
    "anthropic": _anthropic, "gemini": _gemini, "openai": _openai, "openrouter": _openrouter,
    "groq": _groq, "ollama": _ollama, "claude_code": _claude_code,
}
# 공급자별로 받는 선택 옵션. models._call_one이 이 목록에 있는 것만 넘긴다
OPTIONS: dict[str, tuple[str, ...]] = {"anthropic": ("json_schema",), "openai": (), "gemini": ("temperature", "thinking"),
                                       "openrouter": ("temperature", "reasoning"), "groq": ("temperature", "reasoning"),
                                       "ollama": ("temperature", "reasoning"), "claude_code": ("thinking",)}
