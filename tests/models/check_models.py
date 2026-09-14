"""models.py·providers.py 검수 (착수 프롬프트 0단계 6번, DEV_MODE 모델표, 사고·추론 설정, 로컬·Groq 제공자 순서).

실행: uv run python -m tests.models.check_models
- 키 없이 도는 검사: 운영·개발 모델표, 출처, 하드코딩, 429·503·529·연결 실패·타임아웃·키 없음 전환,
  모델 장애(ModelUnavailable), DEV_MODE 전환, 옵션 전달, 호출 간격, 공급자별 변환
- 실제 호출: 개발 모델표 4역할 첫 제공자(로컬)는 성공해야 통과. 운영 모델표는 키가 없으면 SKIP
환경변수 값과 키는 출력하지 않는다.
"""
import json
import os
import re
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("LOCAL_TRACE_LOG", str(Path(tempfile.gettempdir()) / "toolscout_test_trace.jsonl"))

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402

import config  # noqa: E402
import models  # noqa: E402
import providers  # noqa: E402

EXPECTED_PROD = {
    "curator": ("gemini-3.6-flash", "claude-haiku-4-5-20251001"),
    "verifier": ("claude-opus-5", "claude-sonnet-5"),
    "explainer": ("claude-sonnet-5", "gpt-5.6-terra"),
    "gate": ("claude-haiku-4-5-20251001", "gemini-3.6-flash"),
}
SOURCES = ["platform.claude.com/docs", "ai.google.dev/gemini-api/docs/models", "developers.openai.com/api/docs/models",
           "openrouter.ai/api/v1/models", "console.groq.com/docs", "ollama.com/library"]
MODEL_NAME = re.compile(r"claude-(opus|sonnet|haiku|fable)|gemini-\d|gpt-\d|gpt-oss|gemma-?\d|qwen\d|llama\d|nemotron|:free")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY",
           "openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY", "ollama": None}
DEV_ORDER = ["ollama", "groq", "gemini", "openrouter"]
TOOL = {"name": "fetch_article", "description": "기사 원문", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}


class FakeStatus(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


@contextmanager
def dev_mode(value: str | None):
    saved = os.environ.get("DEV_MODE")
    if value is None:
        os.environ.pop("DEV_MODE", None)
    else:
        os.environ["DEV_MODE"] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = saved


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
    """운영 모델표 해설가(기본 anthropic, 대체 openai)로 전환 규칙을 확인한다."""
    calls: list[str] = []
    original = dict(models.PROVIDERS)

    def fake(status: int | None):
        def adapter(model, messages, tools, **_options):
            calls.append(model)
            if status is not None:
                raise FakeStatus(status)
            return AIMessage(content=f"ok:{model}")
        return adapter

    table = models.PROD_MODELS["explainer"]
    models.PROVIDERS[table[0]["provider"]] = fake(primary_status)
    models.PROVIDERS[table[1]["provider"]] = fake(fallback_status)
    try:
        with dev_mode("0"):
            result = models.call("explainer", [HumanMessage("안녕")])
        outcome = {"slot": result.response_metadata.get("slot"), "trace_id": bool(result.response_metadata.get("trace_id"))}
    except models.ModelUnavailable as exc:
        outcome = {"raised": models.status_code(exc.__cause__)}
    finally:
        models.PROVIDERS.update(original)
    return {"calls": len(calls), **outcome}


def dev_chain_case(errors: dict[str, Exception | None]) -> dict:
    """개발 모델표 큐레이터 제공자 순서(ollama→groq→gemini→openrouter). errors: 제공자 → 낼 예외(None이면 성공)."""
    calls: list[str] = []
    original = dict(models.PROVIDERS)

    def fake(name: str):
        def adapter(model, messages, tools, **_options):
            calls.append(name)
            if errors.get(name) is not None:
                raise errors[name]
            return AIMessage(content=f"ok:{name}")
        return adapter

    for name in DEV_ORDER:
        models.PROVIDERS[name] = fake(name)
    try:
        with dev_mode("1"):
            result = models.call("curator", [HumanMessage("안녕")])
        outcome = {"slot": result.response_metadata.get("slot"), "provider": result.response_metadata.get("provider")}
    except models.ModelUnavailable as exc:
        outcome = {"unavailable": len(exc.attempts)}
    finally:
        models.PROVIDERS.update(original)
    return {"calls": calls, **outcome}


def mode_switch() -> bool:
    """DEV_MODE 값에 따라 같은 role 호출이 다른 표로 가는지 확인한다."""
    seen: list[str] = []
    original = dict(models.PROVIDERS)
    for name in models.PROVIDERS:
        models.PROVIDERS[name] = lambda model, messages, tools, _n=name, **_o: seen.append(f"{_n}:{model}") or AIMessage("ok")
    try:
        with dev_mode(None):
            models.call("gate", [HumanMessage("x")])
        with dev_mode("1"):
            models.call("gate", [HumanMessage("x")])
        with dev_mode("0"):
            models.call("gate", [HumanMessage("x")])
    finally:
        models.PROVIDERS.update(original)
    dev = models.DEV_MODELS["gate"][0]
    prod = models.PROD_MODELS["gate"][0]
    return seen == [f"{dev['provider']}:{dev['model']}"] * 2 + [f"{prod['provider']}:{prod['model']}"]


def option_routing() -> bool:
    """온도는 받는 공급자에만, thinking은 Gemini에만, reasoning은 OpenRouter·Groq·Ollama에만 넘어가는지."""
    seen: dict[str, dict] = {}
    original = dict(models.PROVIDERS)

    def recorder(name: str):
        def adapter(model, messages, tools, **kw):
            seen.setdefault(name, kw)
            return AIMessage("ok")
        return adapter

    for name in models.PROVIDERS:
        models.PROVIDERS[name] = recorder(name)
    try:
        with dev_mode("0"):
            models.call("verifier", [HumanMessage("x")], temperature=0)  # anthropic
        with dev_mode("1"):
            for index, spec in enumerate(models.DEV_MODELS["curator"]):  # ollama, groq, gemini, openrouter
                models._call_one("curator", models.SLOT_NAMES[index], spec, [HumanMessage("x")], None, 0)
    finally:
        models.PROVIDERS.update(original)
    return (seen.get("anthropic") == {} and seen.get("openrouter") == {"temperature": 0, "reasoning": "none"}
            and seen.get("gemini") == {"temperature": 0, "thinking": "minimal"}
            and seen.get("ollama") == {"temperature": 0}
            and seen.get("groq") == {"temperature": 0, "reasoning": "low"})


def throttle_spacing() -> bool:
    """개발 모드에서 같은 공급자 연속 호출 사이에 간격이 생기는지."""
    saved = dict(models.FREE_TIER_MIN_INTERVAL)
    models.FREE_TIER_MIN_INTERVAL["test-provider"] = 0.3
    try:
        with dev_mode("1"):
            started = time.monotonic()
            models._throttle("test-provider")
            models._throttle("test-provider")
            elapsed = time.monotonic() - started
    finally:
        models.FREE_TIER_MIN_INTERVAL.clear()
        models.FREE_TIER_MIN_INTERVAL.update(saved)
    return elapsed >= 0.29


def dev_table_rules() -> bool:
    """선별·게이트는 ollama부터, 해설가·검증관은 로컬 모델이 도구 호출을 못 해 groq부터 (docs/local-model.md)."""
    specs = [spec for chain in models.DEV_MODELS.values() for spec in chain]
    order = {role: [s["provider"] for s in chain] for role, chain in models.DEV_MODELS.items()}
    return (set(models.DEV_MODELS) == set(EXPECTED_PROD)
            and order["curator"] == order["gate"] == DEV_ORDER
            and order["explainer"] == order["verifier"] == DEV_ORDER[1:]
            and all(s["model"].endswith(":free") for s in specs if s["provider"] == "openrouter"))


def history(tool_ai: AIMessage) -> list:
    return [SystemMessage("시스템"), HumanMessage("이 기사 요약"), tool_ai,
            ToolMessage("<data>본문</data>", tool_call_id=tool_ai.tool_calls[0]["id"], name="fetch_article")]


def anthropic_conversion() -> bool:
    captured = {}
    block = SimpleNamespace(type="tool_use", name="fetch_article", input={"url": "https://a.com"}, id="tu_1")
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: captured.update(kw) or SimpleNamespace(
        content=[block], usage=SimpleNamespace(input_tokens=3, output_tokens=4), stop_reason="tool_use")))
    providers._anthropic_client = lambda: fake
    first = providers._anthropic("m", [SystemMessage("시스템"), HumanMessage("요약")], [convert_to_openai_tool(TOOL)])
    providers._anthropic("m", history(first), None)
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
    providers._gemini_client = lambda: fake
    first = providers._gemini("m", [HumanMessage("요약")], [convert_to_openai_tool(TOOL)], temperature=0, thinking="minimal")
    cfg = captured["config"]
    tools_ok = (cfg.tools[0].function_declarations[0].name == "fetch_article" and cfg.temperature == 0
                and "minimal" in str(cfg.thinking_config.thinking_level).lower())
    providers._gemini("m", history(first), None)
    tools_ok = tools_ok and captured["config"].thinking_config is None  # thinking을 안 주면 설정하지 않는다
    contents = captured["contents"]
    return (tools_ok and first.tool_calls[0]["args"] == {"url": "https://a.com"}
            and contents[1].parts[0].thought_signature == b"sig"
            and contents[2].parts[0].function_response.name == "fetch_article")


def openai_compatible_conversion() -> dict:
    captured: list[tuple[str, dict]] = []
    reply = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": "fetch_article", "arguments": "{\"url\": \"https://a.com\"}"}}]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2}}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.append((str(request.url), body))
        if body["model"] == "error-model":
            return httpx.Response(200, json={"error": {"message": "rate limited upstream", "code": 429}})
        return httpx.Response(200, json=reply)

    timeouts: list[float] = []
    headers: list[dict] = []

    def client(timeout=providers.REMOTE_TIMEOUT):
        timeouts.append(timeout)
        return httpx.Client(transport=httpx.MockTransport(lambda r: headers.append(dict(r.headers)) or handler(r)))

    providers._http_client = client
    saved_keys = {k: os.environ.get(k) for k in ("OPENAI_API_KEY", "OPENROUTER_API_KEY")}
    os.environ.update({k: "test-key" for k in saved_keys})  # 가짜 전송이라 실제 키가 필요 없다. 끝나면 되돌린다
    try:
        return _openai_compatible_cases(captured, timeouts, headers)
    finally:
        for k, v in saved_keys.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _openai_compatible_cases(captured: list, timeouts: list, headers: list) -> dict:
    first = providers._openai("m", [HumanMessage("요약")], [convert_to_openai_tool(TOOL)])
    providers._openai("m", history(first), None)
    roles = [m["role"] for m in captured[-1][1]["messages"]]
    routed = providers._openrouter("m:free", [HumanMessage("요약")], None, temperature=0, reasoning="none")
    try:
        providers._openrouter("error-model", [HumanMessage("요약")], None)
        body_error = None
    except providers.ProviderError as exc:
        body_error = exc.status_code
    local = providers._ollama("local", [HumanMessage("요약")], None, temperature=0, reasoning="none")
    local_ok = (captured[-1][0] == providers.OLLAMA_URL and captured[-1][1].get("reasoning_effort") == "none"
                and "authorization" not in headers[-1] and timeouts[-1] == providers.LOCAL_TIMEOUT
                and local.response_metadata["provider"] == "ollama")
    saved_groq = os.environ.pop("GROQ_API_KEY", None)
    before = len(captured)
    try:
        providers._groq("g", [HumanMessage("요약")], None)
        missing = False
    except providers.MissingKey:
        missing = len(captured) == before
    finally:
        if saved_groq is not None:
            os.environ["GROQ_API_KEY"] = saved_groq
    return {
        "변환_ollama_주소·키없음·30초·사고끔": local_ok,
        "groq_키없으면_요청없이_MissingKey": missing,
        "변환_openai_httpx": first.tool_calls[0]["id"] == "c1" and roles == ["system", "user", "assistant", "tool"]
        and captured[0][1]["tools"][0]["function"]["name"] == "fetch_article" and "max_completion_tokens" in captured[0][1],
        "변환_openrouter_주소·max_tokens·온도·추론끔": captured[2][0] == providers.OPENROUTER_URL and "max_tokens" in captured[2][1]
        and captured[2][1].get("temperature") == 0 and captured[2][1].get("reasoning") == {"effort": "none"}
        and "temperature" not in captured[0][1] and "reasoning" not in captured[3][1]
        and routed.response_metadata["provider"] == "openrouter",
        "200_본문_오류는_ProviderError_코드보존": body_error == 429 and body_error in models.FALLBACK_STATUS,
    }


def live_calls(table: dict, required: bool) -> dict:
    """운영 모델표: 역할별 첫 모델만 부른다(키 없으면 SKIP). 개발 모델표: 제공자 순서대로 실제 전환하며 부른다."""
    out = {}
    for role, chain in table.items():
        if required:
            try:
                reply = models.call(role, [HumanMessage("안녕이라고만 답해")])
                meta = reply.response_metadata
                out[role] = f"성공 {meta['provider']}:{meta['model']} ({meta['slot']}): {reply.text.strip()[:20]}"
            except models.ModelUnavailable as exc:
                out[role] = f"실패 {config.redact(str(exc))[:160]}"
            continue
        spec = chain[0]
        if KEY_ENV[spec["provider"]] and not os.environ.get(KEY_ENV[spec["provider"]]):
            out[role] = f"SKIP(키 없음) {spec['model']}"
            continue
        try:
            reply = models._call_one(role, "primary", spec, [HumanMessage("안녕이라고만 답해")], None)
            out[role] = f"성공 {spec['model']}: {reply.text.strip()[:20]}"
        except Exception as exc:
            out[role] = f"실패 {spec['model']} {type(exc).__name__}: {config.redact(str(exc))[:120]}"
    return out


def main() -> int:
    text = (ROOT / "models.py").read_text(encoding="utf-8")
    hardcoded = no_hardcoding()
    cases = {code: fallback_case(int(code), None) for code in ("503", "429", "529")}
    cases |= {"400": fallback_case(400, None), "503_후_대체도_503": fallback_case(503, 503)}
    chain_all = dev_chain_case({"ollama": httpx.ReadTimeout("느림"), "groq": providers.MissingKey("GROQ_API_KEY 비어있음"),
                                "gemini": FakeStatus(429), "openrouter": None})
    chain_connect = dev_chain_case({"ollama": httpx.ConnectError("꺼짐"), "groq": None})
    chain_400 = dev_chain_case({"ollama": FakeStatus(400)})
    chain_dead = dev_chain_case({name: FakeStatus(429) for name in DEV_ORDER})
    originals = (providers._anthropic_client, providers._gemini_client, providers._http_client)
    ok = {"calls": 2, "slot": "fallback", "trace_id": True}
    checks = {
        "운영_모델표_CLAUDE_일치": {r: (t[0]["model"], t[1]["model"]) for r, t in models.PROD_MODELS.items()} == EXPECTED_PROD,
        "개발_모델표_순서_ollama→groq→gemini→openrouter": dev_table_rules(),
        "개발_타임아웃·키없음·429_차례로_전환": chain_all == {"calls": DEV_ORDER, "slot": "fallback3", "provider": "openrouter"},
        "개발_연결실패_다음으로": chain_connect == {"calls": ["ollama", "groq"], "slot": "fallback", "provider": "groq"},
        "개발_400은_전환없이_모델장애": chain_400 == {"calls": ["ollama"], "unavailable": 1},
        "개발_전부_429면_모델장애": chain_dead == {"calls": DEV_ORDER, "unavailable": 4},
        "DEV_MODE_전환_기본1": mode_switch(),
        "출처_URL_주석": all(s in text for s in SOURCES),
        "다른_파일_모델명_하드코딩_없음": not hardcoded,
        "503_대체_1회": cases["503"] == ok,
        "429_대체_1회": cases["429"] == ok,
        "529_대체_1회": cases["529"] == ok,
        "400_전환_안함": cases["400"] == {"calls": 1, "raised": 400},
        "대체_실패시_추가_전환_없음": cases["503_후_대체도_503"] == {"calls": 2, "raised": 503},
        "변환_anthropic": anthropic_conversion(),
        "변환_gemini_thought_signature·온도·사고수준": gemini_conversion(),
        "옵션은_받는_공급자에만": option_routing(),
        "개발모드_무료등급_호출간격": throttle_spacing(),
        **openai_compatible_conversion(),
    }
    providers._anthropic_client, providers._gemini_client, providers._http_client = originals
    dev_live = live_calls(models.DEV_MODELS, required=True)
    prod_live = live_calls(models.PROD_MODELS, required=False)
    checks["개발_모델_4역할_실제_호출_성공"] = all(v.startswith("성공") for v in dev_live.values())
    report = {"dev_mode": models.dev_mode(), "checks": checks, "fallback_cases": cases, "hardcoded_files": hardcoded,
              "dev_chain_cases": {"all": chain_all, "connect": chain_connect, "400": chain_400, "dead": chain_dead},
              "live_dev": dev_live, "live_prod": prod_live, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
