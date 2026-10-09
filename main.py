"""FastAPI 앱 진입점: / 화면, /api/ 기능, /mcp MCP 서버, /demo 공개 데모 (계획안 9.3).

실행: uv run uvicorn main:app --port 8000
앱이 떠 있는 동안 06:55 예열·07:00 하루 실행·08:00 발송 예약이 돈다 (pipeline/scheduler.py). SCHEDULER_ENABLED=0이면 끈다.
해설가가 원문을 읽는 MCP 서버가 이 앱의 /mcp라서 포트는 8000으로 띄운다.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

import mcp_server
import models
from agent import tracing
from pipeline import scheduler
from routes import ask, auth, briefings, demo, feedback, google, guard, invite, pages, settings, signup, support, w1
from routes.protect import AllowedStaticFiles, ProtectMiddleware

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


def make_app(docs: bool) -> FastAPI:
    """앱을 만든다. docs가 거짓이면 /docs·/redoc·/openapi.json을 끈다(운영). 생성 시점에 정해져서 검수가 두 모드를 다 만들어 본다."""
    app = FastAPI(title="toolscout", lifespan=lifespan, docs_url="/docs" if docs else None,
                  redoc_url="/redoc" if docs else None, openapi_url="/openapi.json" if docs else None)
    app.add_middleware(ProtectMiddleware)  # AI 크롤러 403·X-Robots-Tag·TDM 헤더 (routes/protect.py)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "service": "toolscout"}

    app.include_router(auth.router)  # 세션·로그아웃·내 정보
    app.include_router(signup.router)  # 이메일 회원가입(인증번호)·비밀번호 로그인
    app.include_router(google.router)  # 구글 로그인
    app.include_router(pages.router)  # 화면 (/login 첫 화면, /signup, /pending, /, /settings, /history, /f)
    app.include_router(settings.router)  # 프로필·기억 지우기·계정 삭제·오늘 브리핑 지금 만들기
    app.include_router(briefings.router)  # 오늘·날짜별 브리핑, 날짜 목록, 키워드 검색
    app.include_router(feedback.router)  # 피드백 버튼(W3): 웹 세션, 메일 서명 링크
    app.include_router(ask.router)  # 질문창(W2): 게이트·키워드 검색·해설가 답
    app.include_router(invite.router)  # 관리자 가입 승인·사용자 관리
    app.include_router(support.router)  # 고객센터 문의(로그인 없이 가능)와 관리자 문의 목록
    app.include_router(demo.router)  # 공개 데모 /demo (로그인 없음, 고정 예시 뉴스)
    app.include_router(guard.router)  # 함정 링크(보이지 않는 링크를 따라온 봇을 24시간 차단)
    app.include_router(w1.router)  # 아침 브리핑 작업을 직접 부르는 API (실행·발송·상태)
    app.mount("/static", AllowedStaticFiles(directory=WEB), name="static")  # 허용 목록 파일만
    app.mount("/mcp", mcp_app)
    return app


app = make_app(docs=models.dev_mode())  # 운영(DEV_MODE=0)에서는 API 지도(/docs)를 닫는다
