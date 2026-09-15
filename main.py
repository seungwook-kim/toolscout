"""FastAPI 앱 진입점: / 화면, /api/ 기능, /mcp MCP 서버 (계획안 9.3).

실행: uv run uvicorn main:app --port 8000
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

import mcp_server
from agent import tracing
from routes import w1

WEB = Path(__file__).parent / "web"

mcp_app = mcp_server.build_app()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # mount한 MCP 하위 앱의 세션 관리자는 여기서 돌려야 한다
    async with mcp_server.mcp.session_manager.run():
        yield
    tracing.flush()


app = FastAPI(title="toolscout", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "toolscout"}


app.include_router(w1.router)  # n8n W1: 하루 실행 시작·상태·발송함·발송 기록


app.mount("/mcp", mcp_app)
