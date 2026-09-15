"""main.py 검수 (착수 프롬프트 12번). uvicorn 프로세스를 실제로 띄워 확인한다.

실행: uv run python -m tests.app.check_main
docker compose up app 확인은 compose 파일이 있는 feat/05-docker 브랜치 검수(tests/env/check_docker.py)로 넘긴다.
"""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[2]
KEY = "test-service-key"
SERVER_LOG = Path(tempfile.gettempdir()) / "toolscout_test_server.log"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(port: int) -> subprocess.Popen:
    """서버 출력은 임시 폴더 로그 파일로 보낸다. 읽지 않는 PIPE는 버퍼가 차면 서버가 멈춘다 (도구 호출 20~40회에서 확인)."""
    env = os.environ | {"MCP_SERVICE_KEY": KEY, "PYTHONDONTWRITEBYTECODE": "1", "SCHEDULER_ENABLED": "0"}  # 검수 서버는 예약을 끈다
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    with SERVER_LOG.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    return proc


async def mcp_tools(base: str) -> list[str]:
    async with httpx2.AsyncClient(headers={"X-Service-Key": KEY}) as http:
        async with Client(streamable_http_client(f"{base}/mcp", http_client=http)) as client:
            return sorted(t.name for t in (await client.list_tools()).tools)


def main() -> int:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(port)
    try:
        index = httpx.get(f"{base}/", timeout=5)
        login_page = httpx.get(f"{base}/login", timeout=5)
        health = httpx.get(f"{base}/api/health", timeout=5)
        no_key = httpx.post(f"{base}/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=5)
        tools = asyncio.run(mcp_tools(base))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    checks = {
        "uvicorn_기동": health.status_code == 200,
        "루트는_로그인으로·로그인_화면": index.status_code == 303 and index.headers.get("location") == "/login"
        and login_page.status_code == 200 and "로그인 링크 받기" in login_page.text,
        "api_health": health.json() == {"status": "ok", "service": "toolscout"},
        "mcp_mount_키없으면_401": no_key.status_code == 401,
        "mcp_mount_도구_6개": len(tools) == 6,
    }
    docker = "docker 없음, feat/05-docker 검수로 넘김" if shutil.which("docker") is None else "docker 있음, 수동 확인 필요"
    report = {"checks": checks, "tools": tools, "docker_compose_up_app": docker, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
