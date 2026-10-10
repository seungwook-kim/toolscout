"""Anthropic 제공자(providers._anthropic, httpx 직접 호출)와 운영 모델표 검수 (2026-10-11, Haiku 5.5 전환). 가짜 HTTP만 쓴다.

실행: uv run python -m tests.models.check_anthropic
- 메시지 변환(system 분리·user·assistant·도구 호출·도구 결과 묶기), 도구 호출 응답 해석, 헤더·주소
- 구조화 출력: ask_json의 규격이 output_config.format 스키마로 가고(모든 object additionalProperties false, 범위 키 없음), 답이 규격대로 읽힘
- 도구가 있는 호출에는 구조화 출력을 붙이지 않음 / 다른 제공자는 스키마를 받지 않음
- 429(60초 뒤 같은 제공자 1회 더)·500·529 전환, 키 없음 오류(요청 없이 MissingKey, 키 값 미노출)
- 운영 모델표: 네 역할과 same_story가 [Haiku 5.5, gpt-4o-mini(OpenRouter)], importance는 모델표에 없음(Jev)
키와 응답 전체는 출력하지 않는다.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("LOCAL_TRACE_LOG", str(Path(tempfile.gettempdir()) / "toolscout_test_trace.jsonl"))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402

import models  # noqa: E402
import providers  # noqa: E402
from agent import schemas, structured  # noqa: E402

results: list[tuple[str, bool]] = []
TOOL = {"name": "fetch_article", "description": "기사 원문", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}
SECRET = "test-fake-secret-value"


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


class Fake:
    """가짜 서버. 요청을 모으고 reply(url, body, 몇번째)가 돌려주는 (상태, 본문)을 응답한다."""

    def __init__(self, reply):
        self.requests: list[tuple[str, dict, dict]] = []
        self.reply = reply

    def client(self, timeout=providers.REMOTE_TIMEOUT):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            self.requests.append((str(request.url), dict(request.headers), body))
            status, data = self.reply(str(request.url), body, len(self.requests))
            return httpx.Response(status, json=data)
        return httpx.Client(transport=httpx.MockTransport(handler))


def message(content: list[dict], stop="end_turn") -> dict:
    return {"type": "message", "role": "assistant", "content": content, "stop_reason": stop,
            "usage": {"input_tokens": 11, "output_tokens": 7}}


def openai_reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def install(fake: Fake) -> None:
    providers._http_client = fake.client


def conversion() -> None:
    tool_msg = AIMessage(content="", tool_calls=[{"name": "fetch_article", "args": {"url": "https://a.com"}, "id": "tu_1", "type": "tool_call"},
                                                 {"name": "fetch_article", "args": {"url": "https://b.com"}, "id": "tu_2", "type": "tool_call"}])
    history = [SystemMessage("시스템"), SystemMessage("둘째"), HumanMessage("요약"), tool_msg,
               ToolMessage("<data>A</data>", tool_call_id="tu_1", name="fetch_article"),
               ToolMessage("<data>B</data>", tool_call_id="tu_2", name="fetch_article"),
               AIMessage("끝"), HumanMessage("고마워")]
    system, payload = providers.anthropic_messages(history)
    roles = [m["role"] for m in payload]
    check("변환: system은 따로 합치고 메시지에는 없음", system == "시스템\n\n둘째" and roles == ["user", "assistant", "user", "assistant", "user"])
    check("변환: assistant 도구 호출은 tool_use 블록, 입력은 dict", payload[1]["content"] == [
        {"type": "tool_use", "id": "tu_1", "name": "fetch_article", "input": {"url": "https://a.com"}},
        {"type": "tool_use", "id": "tu_2", "name": "fetch_article", "input": {"url": "https://b.com"}}])
    check("변환: 연속 도구 결과는 user 한 메시지의 tool_result 블록 둘",
          [b["type"] for b in payload[2]["content"]] == ["tool_result"] * 2 and payload[2]["content"][1]["tool_use_id"] == "tu_2"
          and payload[3]["content"] == [{"type": "text", "text": "끝"}] and payload[4]["content"] == "고마워")


def tool_call_response() -> None:
    fake = Fake(lambda url, body, n: (200, message([{"type": "text", "text": "읽어 볼게요"},
                                                     {"type": "tool_use", "id": "tu_9", "name": "fetch_article", "input": {"url": "https://a.com"}}],
                                                    "tool_use")))
    install(fake)
    os.environ["ANTHROPIC_API_KEY"] = SECRET
    reply = providers._anthropic("claude-x", [SystemMessage("시스템"), HumanMessage("요약")], [convert_to_openai_tool(TOOL)])
    url, headers, body = fake.requests[0]
    check("요청: 주소·x-api-key·anthropic-version·max_tokens", url == providers.ANTHROPIC_URL == "https://api.anthropic.com/v1/messages"
          and headers.get("x-api-key") == SECRET and headers.get("anthropic-version") == "2023-06-01" and body["max_tokens"] == providers.MAX_TOKENS
          and body["system"] == "시스템" and "authorization" not in headers)
    check("요청: 도구는 name·description·input_schema로 변환", body["tools"] == [
        {"name": "fetch_article", "description": "기사 원문", "input_schema": TOOL["parameters"]}] and "output_config" not in body)
    check("응답: 도구 호출·글·토큰·stop_reason 해석", reply.tool_calls == [{"name": "fetch_article", "args": {"url": "https://a.com"}, "id": "tu_9", "type": "tool_call"}]
          and reply.text == "읽어 볼게요" and reply.usage_metadata["input_tokens"] == 11 and reply.usage_metadata["output_tokens"] == 7
          and reply.response_metadata["stop_reason"] == "tool_use" and reply.response_metadata["provider"] == "anthropic")
    # 도구가 있는 호출에는 구조화 출력을 붙이지 않는다
    providers._anthropic("claude-x", [HumanMessage("요약")], [convert_to_openai_tool(TOOL)], json_schema={"type": "object"})
    check("도구가 있으면 구조화 출력 스키마를 붙이지 않음", "output_config" not in fake.requests[-1][2])


def structured_output() -> None:
    answer = {"judgments": [{"id": 1, "ai_related": True, "worth_today": True, "topic": "model_release", "importance": 4, "reason": "새 모델 공개"}]}
    fake = Fake(lambda url, body, n: (200, message([{"type": "text", "text": json.dumps(answer, ensure_ascii=False)}])))
    install(fake)
    os.environ["DEV_MODE"] = "0"
    os.environ["ANTHROPIC_API_KEY"] = SECRET
    stats = structured.Stats()
    parsed = asyncio.run(structured.ask_json("curator", "판정한다", [{"id": 1, "title": "x"}], schemas.SelectionBatch, stats))
    body = fake.requests[0][2]
    fmt = body.get("output_config", {}).get("format", {})
    schema_text = json.dumps(fmt.get("schema", {}))

    def objects_closed(node) -> bool:
        if isinstance(node, dict):
            if node.get("type") == "object" and node.get("additionalProperties") is not False:
                return False
            return all(objects_closed(v) for v in node.values())
        return all(objects_closed(v) for v in node) if isinstance(node, list) else True

    check("구조화 출력: ask_json 규격이 output_config.format json_schema로 감", fmt.get("type") == "json_schema"
          and "judgments" in fmt.get("schema", {}).get("properties", {}) and body["model"] == "claude-haiku-5-5")
    check("구조화 출력: 모든 object additionalProperties false, 범위 키(minLength·minimum 등) 없음",
          objects_closed(fmt.get("schema")) and not any(k in schema_text for k in ('"minLength"', '"maxLength"', '"minimum"', '"maximum"')))
    check("구조화 출력: 답이 규격 객체로 읽히고 형식 실패 0", parsed is not None and parsed.judgments[0].topic == "model_release"
          and stats.format_failures == 0 and stats.unrecovered == 0 and stats.input_tokens == 11)
    check("구조화 출력: 호출이 끝나면 스키마 설정을 되돌림", models.STRUCTURED_SCHEMA.get() is None)
    # 다른 제공자는 스키마를 받지 않는다
    seen: dict = {}
    original = dict(models.PROVIDERS)
    models.PROVIDERS["openrouter"] = lambda model, messages, tools, **kw: seen.update(kw) or AIMessage("{}")
    token = models.STRUCTURED_SCHEMA.set({"type": "object"})
    try:
        models._call_one("gate", "primary", models.OPENROUTER_MINI, [HumanMessage("x")], None, 0)
    finally:
        models.STRUCTURED_SCHEMA.reset(token)
        models.PROVIDERS.update(original)
    check("다른 제공자(OpenRouter)에는 스키마를 안 넘김", seen == {"temperature": 0})


def retries_and_keys() -> None:
    waits: list[float] = []
    models._sleep = waits.append

    def run(reply) -> tuple[Fake, object]:
        fake = Fake(reply)
        install(fake)
        os.environ["DEV_MODE"] = "0"
        os.environ["ANTHROPIC_API_KEY"] = SECRET
        os.environ["OPENROUTER_API_KEY"] = "or-test"
        try:
            return fake, models.call("explainer", [HumanMessage("안녕")], temperature=0)
        except models.ModelUnavailable as exc:
            return fake, exc

    def host(fake: Fake) -> list[str]:
        return [httpx.URL(u).host for u, _, _ in fake.requests]

    ok = message([{"type": "text", "text": "안녕"}])
    fake, reply = run(lambda url, body, n: (429, {"error": {"message": "rate"}}) if n == 1 else (200, ok))
    check("429: 60초 기다렸다가 같은 제공자(Anthropic)에 한 번 더", host(fake) == ["api.anthropic.com"] * 2 and waits[-1:] == [60]
          and reply.response_metadata["slot"] == "primary")
    fake, reply = run(lambda url, body, n: (200, openai_reply("대체")) if "openrouter" in url else (500, {"error": {}}))
    check("500: 다음 칸(OpenRouter gpt-4o-mini)으로 전환", host(fake) == ["api.anthropic.com", "openrouter.ai"]
          and reply.response_metadata["slot"] == "fallback" and reply.text == "대체")
    fake, reply = run(lambda url, body, n: (200, openai_reply("대체")) if "openrouter" in url else (529, {"error": {}}))
    check("529(과부하): 다음 칸으로 전환", host(fake) == ["api.anthropic.com", "openrouter.ai"] and reply.text == "대체")
    fake, reply = run(lambda url, body, n: (400, {"error": {"message": "bad"}}))
    check("400: 전환 없이 모델 장애", host(fake) == ["api.anthropic.com"] and isinstance(reply, models.ModelUnavailable))
    fake, reply = run(lambda url, body, n: (429, {"error": {}}))
    check("429가 계속되면 Anthropic 2번 뒤 다음 칸도 429면 모델 장애",
          host(fake).count("api.anthropic.com") == 2 and isinstance(reply, models.ModelUnavailable))

    os.environ.pop("ANTHROPIC_API_KEY", None)
    fake = Fake(lambda url, body, n: (200, openai_reply("대체")))
    install(fake)
    os.environ["OPENROUTER_API_KEY"] = "or-test"
    try:
        providers._anthropic("m", [HumanMessage("x")], None)
        raised = None
    except providers.MissingKey as exc:
        raised = str(exc)
    check("키 없음: 요청 없이 MissingKey(키 이름만, 값 없음)", raised == "ANTHROPIC_API_KEY 비어있음" and fake.requests == [])
    os.environ["DEV_MODE"] = "0"
    reply = models.call("gate", [HumanMessage("x")])
    check("키 없음이면 둘째 칸(OpenRouter)으로 넘어감", reply.text == "대체" and reply.response_metadata["slot"] == "fallback")
    os.environ["ANTHROPIC_API_KEY"] = SECRET
    fake = Fake(lambda url, body, n: (401, {"error": {"message": "invalid x-api-key"}}))
    install(fake)
    try:
        providers._anthropic("m", [HumanMessage("x")], None)
        leaked = True
    except httpx.HTTPStatusError as exc:
        leaked = SECRET in str(exc) or SECRET in repr(exc)
    check("401 오류 글에 키 값이 없음", leaked is False)


def prod_table() -> None:
    prod = {**models.PROD_MODELS, **models.SINGLE_MODEL_ROLES}
    want = [{"provider": "anthropic", "model": "claude-haiku-5-5"}, {"provider": "openrouter", "model": "openai/gpt-4o-mini"}]
    os.environ["DEV_MODE"] = "0"
    active = models.active_models()
    check("운영 모델표: 네 역할과 same_story가 [Haiku 5.5, gpt-4o-mini(OpenRouter)]",
          set(prod) == {"curator", "verifier", "explainer", "gate", "same_story"} and all(prod[r] == want for r in prod) and active == prod)
    check("운영 모델표: importance는 없음(Jev)", "importance" not in active)
    os.environ["DEV_MODE"] = "1"
    check("개발 모델표는 그대로(구독만)", all(s["provider"] == "claude_code" for c in models.active_models().values() for s in c))


saved_env = {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "DEV_MODE")}
saved_client, saved_sleep = providers._http_client, models._sleep
try:
    conversion()
    tool_call_response()
    structured_output()
    retries_and_keys()
    prod_table()
finally:
    providers._http_client, models._sleep = saved_client, saved_sleep
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
