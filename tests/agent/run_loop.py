"""agent/loop.py 검수 (착수 프롬프트 10번).

실행: uv run python -m tests.agent.run_loop
- 루프 동작: 정해진 순서로 답하는 가짜 모델로 도구 없음, 도구 1개(실제 MCP 서버), 허용 밖 도구, max_steps 초과를 확인한다
- 실제 모델: 현재 모델표(DEV_MODE면 개발 모델)의 해설가로 "안녕"과 fetch_article 1개 호출. 통과에 포함한다
"""
import asyncio
import json
import logging
import os
import sys

from langchain_core.messages import AIMessage, ToolMessage

import config
import models
from agent import loop, tracing
from tests.app.check_main import KEY, free_port, start

ARTICLE = "https://github.com/modelcontextprotocol/python-sdk"


def scripted(*replies: AIMessage):
    """호출될 때마다 다음 답을 돌려주는 가짜 모델. 받은 메시지를 기록한다."""
    seen: list[list] = []

    def call(role, messages, tools=None):
        seen.append(list(messages))
        return replies[min(len(seen), len(replies)) - 1]
    call.seen = seen
    return call


def tool_call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


async def mechanics(mcp_url: str) -> dict:
    events: list[dict] = []
    notices: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: notices.append(record.getMessage())
    loop.log.addHandler(handler)
    loop._notice["shown"] = False
    hello = scripted(AIMessage('{"reply": "안녕하세요"}'))
    no_tool = await loop.run("explainer", "짧게 답한다.", "안녕", [], 3, on_event=events.append, model_call=hello)

    fetch = scripted(tool_call("fetch_article", {"url": ARTICLE}), AIMessage('```json\n{"summary": "읽음"}\n```'))
    one_tool = await loop.run("explainer", "기사를 읽고 요약한다.", ARTICLE, ["fetch_article"], 3,
                              mcp_url=mcp_url, briefing_user=1, model_call=fetch)
    tool_msg = next((m for m in fetch.seen[-1] if isinstance(m, ToolMessage)), None)
    tool_result = json.loads(tool_msg.content) if tool_msg else {}

    blocked = scripted(tool_call("probe_mcp", {"install_command": "npx x", "kind": "npm"}), AIMessage('{"done": true}'))
    not_allowed = await loop.run("verifier", "검증한다.", "x", ["fetch_article"], 3, mcp_url=mcp_url, model_call=blocked)
    blocked_msg = next(m for m in blocked.seen[-1] if isinstance(m, ToolMessage))

    forever = scripted(tool_call("fetch_article", {"url": ARTICLE}))
    capped = await loop.run("explainer", "요약한다.", "x", ["fetch_article"], 2, mcp_url=mcp_url, model_call=forever)
    loop.log.removeHandler(handler)
    expected_notices = 1 if models.dev_mode() else 0

    first_user = hello.seen[0][1].content
    return {
        "no_tool": no_tool, "one_tool": {k: v for k, v in one_tool.items()}, "capped": capped,
        "events": [e["type"] for e in events],
        "checks": {
            "도구없음_최종_JSON": no_tool["status"] == "ok" and no_tool["output"] == {"reply": "안녕하세요"} and no_tool["steps"] == 1,
            "trace_id_발급": bool(no_tool["trace_id"]) and bool(one_tool["trace_id"]),
            "입력_data_감싸기": first_user.startswith("<data>") and first_user.rstrip().endswith("</data>"),
            "이벤트_콜백": [e["type"] for e in events] == ["model_call", "final"],
            "도구1개_MCP_경유_재호출": one_tool["status"] == "ok" and one_tool["steps"] == 2 and one_tool["tool_calls"] == 1
            and tool_result.get("status") == "ok" and tool_result.get("text", "").startswith("<data"),
            "코드블록_JSON_해석": one_tool["output"] == {"summary": "읽음"},
            "허용밖_도구_거부": not_allowed["status"] == "ok" and json.loads(blocked_msg.content)["status"] == "rejected",
            "max_steps_초과_확인필요": capped["status"] == "확인 필요" and capped["tool_calls"] == 2,
            "개발모드_안내_로그_한번": notices.count(loop.DEV_MODE_NOTICE) == expected_notices,
        },
    }


async def live(mcp_url: str) -> dict:
    """현재 모델표(DEV_MODE면 개발 모델)의 해설가로 실제 실행한다. 제공자 순서대로 전환되며, 쓴 제공자를 남긴다."""
    out: dict = {"chain": [f"{s['provider']}:{s['model']}" for s in models.active_models()["explainer"]]}
    try:
        hello = await loop.run("explainer", '한국어로 짧게 답하고 {"reply": "..."} JSON만 출력한다.', "안녕", [], 2)
        tool = await loop.run("explainer", '반드시 fetch_article 도구로 기사를 읽은 뒤 {"summary": "..."} JSON 한 줄로 요약한다.',
                              ARTICLE, ["fetch_article"], 4, mcp_url=mcp_url, briefing_user=1)
    except Exception as exc:
        while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:  # MCP 클라이언트 TaskGroup이 감싼 원인을 꺼낸다
            exc = exc.exceptions[0]
        out["error"] = f"{type(exc).__name__}: {config.redact(str(exc))[:300]}"
        out["checks"] = {"실제_안녕": False, "실제_도구1개": False}
        return out
    out.update(hello=hello, one_tool=tool, trace_urls=[tracing.trace_url(hello["trace_id"]), tracing.trace_url(tool["trace_id"])],
               used=[f"{r.get('provider')}:{r.get('model')}" for r in (hello, tool)])
    out["checks"] = {
        "실제_안녕": hello["status"] == "ok" and isinstance(hello["output"], dict),
        "실제_도구1개": tool["status"] == "ok" and tool["tool_calls"] >= 1,
    }
    return out


def main() -> int:
    os.environ["MCP_SERVICE_KEY"] = KEY
    port = free_port()
    proc = start(port)
    mcp_url = f"http://127.0.0.1:{port}/mcp"
    try:
        report = asyncio.run(mechanics(mcp_url))
        report["live"] = asyncio.run(live(mcp_url))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        tracing.flush()
    report["tracing_mode"] = tracing.mode()
    report["pass"] = all(report["checks"].values()) and all(report["live"]["checks"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
