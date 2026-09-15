"""FastAPI 앱 진입점: / 화면, /api/ 기능, /mcp MCP 서버 (계획안 9.3).

실행: uv run uvicorn main:app --port 8000
앱이 떠 있는 동안 06:55 예열·07:00 하루 실행·08:00 발송 예약이 돈다 (pipeline/scheduler.py). SCHEDULER_ENABLED=0이면 끈다.
해설가가 원문을 읽는 MCP 서버가 이 앱의 /mcp라서 포트는 8000으로 띄운다.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import mcp_server
from agent import tracing
from pipeline import scheduler
from routes import auth, pages, w1

WEB = Path(__file__).parent / "web"

mcp_app = mcp_server.build_app()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # mount한 MCP 하위 앱의 세션 관리자는 여기서 돌려야 한다
    async with mcp_server.mcp.session_manager.run():
        if scheduler.enabled():
            scheduler.scheduler.start()
        yield
        await scheduler.scheduler.stop()
    tracing.flush()


app = FastAPI(title="toolscout", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "toolscout"}


app.include_router(auth.router)  # 로그인·세션
app.include_router(pages.router)  # 화면 (/, /login, /settings, /history, /f)
app.include_router(w1.router)  # 아침 브리핑 작업을 직접 부르는 API (실행·발송·상태)
app.mount("/static", StaticFiles(directory=WEB), name="static")
app.mount("/mcp", mcp_app)
