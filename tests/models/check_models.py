"""models.py 검수 (착수 프롬프트 0단계 6번).

실행: uv run python -m tests.models.check_models
키 없이 도는 검사(표, 출처, 하드코딩, 429·503 전환, 공급자별 변환)와 키가 있을 때만 도는 실제 호출로 나뉜다.
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("LOCAL_TRACE_LOG", str(Path(tempfile.gettempdir()) / "toolscout_test_trace.jsonl"))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402

import models  # noqa: E402

EXPECTED = {
    "curator": ("gemini-3.6-flash", "claude-haiku-4-5-20251001"),
    "verifier": ("claude-opus-5", "claude-sonnet-5"),
    "explainer": ("claude-sonnet-5", "gpt-5.6-terra"),
    "gate": ("claude-haiku-4-5-20251001", "gemini-3.6-flash"),
}
SOURCES = ["platform.claude.com/docs", "ai.google.dev/gemini-api/docs/models", "developers.openai.com/api/docs/models"]
MODEL_NAME = re.compile(r"claude-(opus|sonnet|haiku|fable)|gemini-\d|gpt-\d")
TOOL = {"name": "fetch_article", "description": "기사 원문", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}


class FakeStatus(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def no_hardcoding() -> list[str]:
    hits = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == "models.py" or rel.startswith((".venv/", "tests/")):
            continue
        if MODEL_NAME.search(path.read_text(encoding="utf-8")):
            hits.append(rel)
    return hits


def fallback_case(primary_status: int | None, fallback_status: int | None) -> dict:
    calls: list[str] = []
    original = dict(models.PROVIDERS)

    def fake(provider: str, status: int | None):
        def adapter(model, messages, tools):
            calls.append(model)
            if status is not None:
                raise FakeStatus(status)
            return AIMessage(content=f"ok:{model}")
        return adapter

    table = models.MODELS["explainer"]
    models.PROVIDERS[table["primary"]["provider"]] = fake("p", primary_status)
    models.PROVIDERS[table["fallback"]["provider"]] = fake("f", fallback_status)
    try:
        result = models.call("explainer", [HumanMessage("안녕")])
        outcome = {"slot": result.response_metadata.get("slot"), "trace_id": bool(result.response_metadata.get("trace_id"))}
    except FakeStatus as exc:
        outcome = {"raised": exc.status_code}
    finally:
        models.PROVIDERS.update(original)
    return {"calls": len(calls), **outcome}


def history(tool_ai: AIMessage) -> list:
    return [SystemMessage("시스템"), HumanMessage("이 기사 요약"), tool_ai,
            ToolMessage("<data>본문</data>", tool_call_id=tool_ai.tool_calls[0]["id"], name="fetch_article")]


def anthropic_conversion() -> bool:
    captured = {}
    block = SimpleNamespace(type="tool_use", name="fetch_article", input={"url": "https://a.com"}, id="tu_1")
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: captured.update(kw) or SimpleNamespace(
        content=[block], usage=SimpleNamespace(input_tokens=3, output_tokens=4), stop_reason="tool_use")))
    models._anthropic_client = lambda: fake
    first = models._anthropic("m", [SystemMessage("시스템"), HumanMessage("요약")], [models.convert_to_openai_tool(TOOL)])
    models._anthropic("m", history(first), None)
    msgs = captured["messages"]
    return (first.tool_calls[0]["name"] == "fetch_article" and captured["system"] == "시스템"
            and msgs[1]["content"][0]["type"] == "tool_use" and msgs[2]["content"][0]["type"] == "tool_result")


def gemini_conversion() -> bool:
    from google.genai import types

    captured = {}
    part = types.Part(function_call=types.FunctionCall(name="fetch_article", args={"url": "https://a.com"}), thought_signature=b"sig")
    response = SimpleNamespace(candidates=[SimpleNamespace(content=types.Content(role="model", parts=[part]), finish_reason="STOP")],
                               usage_metadata=None)
    fake = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: captured.update(kw) or response))
    models._gemini_client = lambda: fake
    first = models._gemini("m", [HumanMessage("요약")], [models.convert_to_openai_tool(TOOL)])
    tools_ok = captured["config"].tools[0].function_declarations[0].name == "fetch_article"
    models._gemini("m", history(first), None)
    contents = captured["contents"]
    return (tools_ok and first.tool_calls[0]["args"] == {"url": "https://a.com"}
            and contents[1].parts[0].thought_signature == b"sig"
            and contents[2].parts[0].function_response.name == "fetch_article")


def openai_conversion() -> bool:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "fetch_article", "arguments": "{\"url\": \"https://a.com\"}"}}]}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2}})

    models._http_client = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    first = models._openai("m", [HumanMessage("요약")], [models.convert_to_openai_tool(TOOL)])
    tools_ok = captured["body"]["tools"][0]["function"]["name"] == "fetch_article"
    models._openai("m", history(first), None)
    roles = [m["role"] for m in captured["body"]["messages"]]
    return tools_ok and first.tool_calls[0]["id"] == "c1" and roles == ["system", "user", "assistant", "tool"]


def live_calls() -> dict:
    need = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}
    out = {}
    for role, table in models.MODELS.items():
        provider = table["primary"]["provider"]
        if not os.environ.get(need[provider]):
            out[role] = "미실행(키 없음)"
            continue
        try:
            reply = models.call(role, [HumanMessage("안녕이라고만 답해")])
            out[role] = f"성공 {reply.response_metadata.get('model')}: {reply.text[:20]}"
        except Exception as exc:
            out[role] = f"실패 {type(exc).__name__}: {str(exc)[:120]}"
    return out


def main() -> int:
    text = (ROOT / "models.py").read_text(encoding="utf-8")
    hardcoded = no_hardcoding()
    cases = {"503": fallback_case(503, None), "429": fallback_case(429, None),
             "400": fallback_case(400, None), "503_후_대체도_503": fallback_case(503, 503)}
    originals = (models._anthropic_client, models._gemini_client, models._http_client)
    checks = {
        "모델표_일치": {r: (t["primary"]["model"], t["fallback"]["model"]) for r, t in models.MODELS.items()} == EXPECTED,
        "출처_URL_주석": all(s in text for s in SOURCES),
        "다른_파일_모델명_하드코딩_없음": not hardcoded,
        "503_대체_1회": cases["503"] == {"calls": 2, "slot": "fallback", "trace_id": True},
        "429_대체_1회": cases["429"] == {"calls": 2, "slot": "fallback", "trace_id": True},
        "400_전환_안함": cases["400"] == {"calls": 1, "raised": 400},
        "대체_실패시_추가_전환_없음": cases["503_후_대체도_503"] == {"calls": 2, "raised": 503},
        "변환_anthropic": anthropic_conversion(),
        "변환_gemini_thought_signature_보존": gemini_conversion(),
        "변환_openai_httpx": openai_conversion(),
    }
    models._anthropic_client, models._gemini_client, models._http_client = originals
    report = {"checks": checks, "fallback_cases": cases, "hardcoded_files": hardcoded,
              "live_calls": live_calls(), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
