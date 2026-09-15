"""웹앱 화면 (계획안 9.3 "/는 화면"). 정적 HTML을 돌려주고 데이터는 화면의 JS가 /api/로 가져온다.

- /login: 로그인 / /: 오늘 브리핑 / /settings: 프로필·설정 / /history: 지난 브리핑 / /f: 메일 피드백 링크 결과
- 로그인이 필요한 화면은 세션이 없으면 /login으로, 프로필이 비었으면 /settings로 보낸다
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse

from routes.auth import current_user, profile_done

WEB = Path(__file__).resolve().parents[1] / "web"
router = APIRouter(include_in_schema=False)


def _page(name: str) -> FileResponse:
    return FileResponse(WEB / name, headers={"Cache-Control": "no-store"})


@router.get("/")
def today(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not profile_done(user):
        return RedirectResponse("/settings", status_code=303)
    return _page("index.html")


@router.get("/login")
def login(request: Request):
    return RedirectResponse("/", status_code=303) if current_user(request) else _page("login.html")


@router.get("/settings")
def settings(request: Request):
    return _page("settings.html") if current_user(request) else RedirectResponse("/login", status_code=303)


@router.get("/history")
def history(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page("history.html") if profile_done(user) else RedirectResponse("/settings", status_code=303)


@router.get("/f")
def feedback_link():
    return _page("f.html")
