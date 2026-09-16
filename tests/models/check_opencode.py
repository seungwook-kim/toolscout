"""OpenCode Zen 어댑터·정책 검수 (2026-09-16 사용자 요청). 가짜 HTTP·가짜 공급자로 확인한다. 실제 호출은 try_opencode.py.

실행: uv run python -m tests.models.check_opencode
- 요청 변환: instructions, input(user·assistant·function_call·function_call_output), 평평한 function 도구, max_output_tokens, store false, 온도 안 넘김
- 응답 변환: output_text → 본문, function_call → tool_calls(args dict), usage, reasoning 항목은 무시
- 오류: 400 본문의 오류 종류·문구를 ProviderError로(전환 안 함), 키 없으면 요청 없이 MissingKey
- 정책: allow_user_text False 모델은 해설가·게이트와 운영 모드에서 건너뜀, 큐레이터·검증관(개발 모드)은 씀.
  opencode 429는 60초 기다리지 않고 다음, 404·401·403도 다음, 다른 제공자의 404는 전과 같이 전환 안 함
"""
import json
import os
import sys
from contextlib import contextmanager

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

import models
import providers

TOOL = {"name": "fetch_article", "description": "기사 원문", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}
RESPONSE = {"status": "completed", "usage": {"input_tokens": 12, "output_tokens": 7}, "output": [
    {"type": "reasoning", "id": "rs_1", "summary": []},
    {"type": "function_call", "id": "fc_1", "call_id": "call_1", "name": "fetch_article", "arguments": "{\"url\": \"https://a.test/x\"}"},
    {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "{\"ok\": true}"}]}]}


class FakeStatus(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


@contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def fake_http(status: int, body: dict, captured: list):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), json.loads(request.content), request.headers.get("authorization", "")))
        return httpx.Response(status, json=body)
    return lambda timeout=providers.REMOTE_TIMEOUT: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout)


def conversion() -> dict:
    captured: list = []
    original = providers._http_client
    providers._http_client = fake_http(200, RESPONSE, captured)
    try:
        with env(OPENCODE_API_KEY="test-key"):
            first = providers._opencode("m", [SystemMessage("시스템"), HumanMessage("요약")], [convert_to_openai_tool(TOOL)])
            history = [SystemMessage("시스템"), HumanMessage("요약"), AIMessage("", tool_calls=first.tool_calls),
                       ToolMessage("<data>본문</data>", tool_call_id="call_1", name="fetch_article")]
            providers._opencode("m", history, None)
        providers._http_client = fake_http(400, {"error": {"type": "MissingSessionID", "message": "free tier can only be used in OpenCode"}}, captured)
        with env(OPENCODE_API_KEY="test-key"):
            try:
                providers._opencode("m", [HumanMessage("요약")], None)
                error = None
            except providers.ProviderError as exc:
                error = exc
        before = len(captured)
        with env(OPENCODE_API_KEY=None):
            try:
                providers._opencode("m", [HumanMessage("요약")], None)
                missing = False
            except providers.MissingKey:
                missing = len(captured) == before
    finally:
        providers._http_client = original
    url, body, auth = captured[0]
    _, second, _ = captured[1]
    return {
        "요청_주소·instructions·input·도구·토큰·store": url == providers.OPENCODE_URL and body["instructions"] == "시스템"
        and body["input"] == [{"role": "user", "content": "요약"}] and body["tools"][0] == {"type": "function", **TOOL}
        and body["max_output_tokens"] == providers.MAX_TOKENS and body["store"] is False and "temperature" not in body
        and auth == "Bearer test-key",
        "응답_본문·tool_calls·usage·reasoning무시": first.text == "{\"ok\": true}" and first.tool_calls[0]["args"] == {"url": "https://a.test/x"}
        and first.tool_calls[0]["id"] == "call_1" and first.usage_metadata["output_tokens"] == 7 and len(first.tool_calls) == 1,
        "왕복_function_call·function_call_output": [i.get("type") or i.get("role") for i in second["input"]] == ["user", "function_call", "function_call_output"]
        and second["input"][2] == {"type": "function_call_output", "call_id": "call_1", "output": "<data>본문</data>"},
        "400_본문_오류종류_보존·전환안함": error is not None and "MissingSessionID" in str(error) and error.status_code == 400
        and models.failover_reason(error, "opencode") is None,
        "키없으면_요청없이_MissingKey": missing,
    }


def chain(table: dict, errors: dict, role: str, dev: str = "1") -> dict:
    calls, waits = [], []
    original_providers, original_sleep = dict(models.PROVIDERS), models._sleep
    original_tables = {id(t): dict(t) for t in (models.DEV_MODELS, models.PROD_MODELS)}

    def fake(name):
        def adapter(model, messages, tools, **_options):
            calls.append(name)
            error = errors.get(name)
            if isinstance(error, list):
                error = error.pop(0) if error else None
            if error:
                raise error
            return AIMessage(f"ok:{name}")
        return adapter

    for name in ("opencode", "ollama", "groq", "gemini"):
        models.PROVIDERS[name] = fake(name)
    models.DEV_MODELS.update(table)
    models.PROD_MODELS.update(table)  # 운영 모드 검사도 같은 가짜 표로
    models._sleep = waits.append
    try:
        with env(DEV_MODE=dev):
            reply = models.call(role, [HumanMessage("x")])
        return {"calls": calls, "provider": reply.response_metadata["provider"], "waits": waits}
    except models.ModelUnavailable as exc:
        return {"calls": calls, "unavailable": exc.attempts, "waits": waits}
    finally:
        models.PROVIDERS.clear()
        models.PROVIDERS.update(original_providers)
        for table_ in (models.DEV_MODELS, models.PROD_MODELS):
            table_.clear()
            table_.update(original_tables[id(table_)])
        models._sleep = original_sleep


def policy() -> dict:
    free = models.OPENCODE_FREE
    ollama, groq = {"provider": "ollama", "model": "o"}, {"provider": "groq", "model": "g"}
    table = {role: [free, ollama, groq] for role in ("curator", "verifier", "explainer", "gate")}
    curator = chain(table, {}, "curator")
    explainer = chain(table, {}, "explainer")
    gate = chain(table, {}, "gate")
    rate = chain(table, {"opencode": FakeStatus(429)}, "verifier")
    gone = chain(table, {"opencode": FakeStatus(404)}, "curator")
    auth = chain(table, {"opencode": FakeStatus(401)}, "curator")
    other_404 = chain({"curator": [ollama, groq]}, {"ollama": FakeStatus(404)}, "curator")
    shipped = [s for role in ("explainer", "gate") for chain_ in (models.DEV_MODELS[role], models.PROD_MODELS[role]) for s in chain_]
    return {
        "학습사용_모델은_큐레이터·검증관에만": curator["calls"] == ["opencode"] and chain(table, {}, "verifier")["calls"] == ["opencode"],
        "해설가·게이트는_건너뜀": explainer["calls"] == ["ollama"] and gate["calls"] == ["ollama"],
        "운영모드에서는_건너뜀": chain(table, {}, "curator", dev="0")["calls"] == ["ollama"],
        "opencode_429는_기다리지않고_다음": rate["calls"] == ["opencode", "ollama"] and rate["waits"] == [],
        "opencode_404·401은_다음": gone["calls"] == ["opencode", "ollama"] and auth["calls"] == ["opencode", "ollama"],
        "다른_제공자_404는_전과_같이_전환안함": other_404["calls"] == ["ollama"] and "unavailable" in other_404,
        "실제_표의_해설가·게이트에_학습사용_모델_없음": all(s.get("allow_user_text") is not False for s in shipped),
        "슬롯이름_5개": len(models.SLOT_NAMES) >= max(len(c) for c in models.DEV_MODELS.values()),
    }


def main() -> int:
    checks = conversion() | policy()
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
