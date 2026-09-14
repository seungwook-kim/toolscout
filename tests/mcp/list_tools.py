"""MCP 서버 검수 (착수 프롬프트 11번). 실제 HTTP로 띄워 SDK 클라이언트로 부른다.

실행: uv run python -m tests.mcp.list_tools
결과: tests/mcp/list_tools_result.json
"""
import asyncio
import json
import os
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import httpx2
import uvicorn
from fastapi import FastAPI
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

KEY = "test-service-key"
os.environ["MCP_SERVICE_KEY"] = KEY

import mcp_server  # noqa: E402

OUT = Path(__file__).with_name("list_tools_result.json")


def make_app() -> FastAPI:
    mcp_app = mcp_server.build_app()

    @asynccontextmanager
    async def lifespan(_app):
        async with mcp_server.mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", mcp_app)
    return app


def serve() -> tuple[uvicorn.Server, str]:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(make_app(), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


def payload(result) -> dict:
    data = getattr(result, "structured_content", None)
    if data is None:
        data = json.loads(result.content[0].text)
    return data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data


async def with_client(url: str, headers: dict, fn):
    async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=60)) as http:
        async with Client(streamable_http_client(url, http_client=http)) as client:
            return await fn(client)


async def checks(base: str) -> dict:
    headers = {"X-Service-Key": KEY, "X-Briefing-User": "1"}
    names = await with_client(f"{base}/mcp/", headers, lambda c: c.list_tools())
    tool_names = sorted(t.name for t in names.tools)

    async def calls(c):
        return {
            "other_domain": payload(await c.call_tool("fetch_article", {"url": "https://example.com/post"})),
            "other_user": payload(await c.call_tool("get_user_memory", {"user_id": 2})),
            "not_implemented": payload(await c.call_tool("lookup_registry", {"name_or_url": "notion"})),
            # 긱뉴스 HTML은 봇 UA에 403을 줘서, 누구에게나 응답하는 허용 도메인 페이지로 확인한다
            "allowed_fetch": payload(await c.call_tool("fetch_article", {"url": "https://github.com/modelcontextprotocol/python-sdk"})),
        }

    results = await with_client(f"{base}/mcp/", headers, calls)
    try:
        no_slash = len((await with_client(f"{base}/mcp", headers, lambda c: c.list_tools())).tools)
    except Exception as exc:
        no_slash = f"{type(exc).__name__}: {str(exc)[:120]}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    accept = {"Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient() as raw:
        no_key = (await raw.post(f"{base}/mcp/", json=body, headers=accept)).status_code
        wrong_key = (await raw.post(f"{base}/mcp/", json=body, headers=accept | {"X-Service-Key": "wrong"})).status_code
    fetched = results["allowed_fetch"]
    return {
        "tools": tool_names,
        "no_key_status": no_key,
        "wrong_key_status": wrong_key,
        "mcp_without_trailing_slash": no_slash,
        "calls": {k: ({kk: vv for kk, vv in v.items() if kk != "text"} | {"text_head": v.get("text", "")[:60]}) for k, v in results.items()},
        "checks": {
            "tools_list_6개": tool_names == sorted(mcp_server.TOOL_NAMES),
            "키_없으면_401": no_key == 401,
            "틀린_키_401": wrong_key == 401,
            "허용_밖_도메인_rejected": results["other_domain"]["status"] == "rejected",
            "다른_사용자_rejected": results["other_user"]["status"] == "rejected",
            "미구현_도구_not_implemented": results["not_implemented"]["status"] == "not_implemented",
            "허용_도메인_data_감싸기_3000자": fetched["status"] == "ok" and fetched["text"].startswith("<data")
            and len(fetched["text"]) <= mcp_server.ARTICLE_LIMIT + 100,
        },
    }


def main() -> int:
    server, base = serve()
    try:
        report = asyncio.run(checks(base))
    finally:
        server.should_exit = True
    report["pass"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
