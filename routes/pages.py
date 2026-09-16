"""웹앱 화면 (계획안 9.3 "/는 화면"). 정적 HTML을 돌려주고 데이터는 화면의 JS가 /api/로 가져온다.

- /login: 로그인 / /: 오늘 브리핑 / /settings: 프로필·설정 / /history: 지난 브리핑 / /f: 메일 피드백 링크 결과
- /invite: 초대 코드 입력 (승인 전 사용자가 보는 유일한 화면) / /admin/invites: 관리자 코드·가입 관리
- 로그인이 필요한 화면은 세션이 없으면 /login으로, 승인 전이면 /invite로, 프로필이 비었으면 /settings로 보낸다
- 공개 데모 /demo는 routes/demo.py에 있다. 색인은 /demo만 허용하고 나머지 화면은 noindex (2026-09-16 사용자 결정)
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from routes.auth import approved, current_user, is_admin, profile_done

WEB = Path(__file__).resolve().parents[1] / "web"
router = APIRouter(include_in_schema=False)
ROBOTS = "User-agent: *\nAllow: /demo\nDisallow: /\n"


def _page(name: str) -> FileResponse:
    return FileResponse(WEB / name, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    return PlainTextResponse(ROBOTS)


@router.get("/")
def today(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not approved(user):
        return RedirectResponse("/invite", status_code=303)
    if not profile_done(user):
        return RedirectResponse("/settings", status_code=303)
    return _page("index.html")


@router.get("/login")
def login(request: Request):
    return RedirectResponse("/", status_code=303) if current_user(request) else _page("login.html")


@router.get("/invite")
def invite(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/", status_code=303) if approved(user) else _page("invite.html")


@router.get("/settings")
def settings(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page("settings.html") if approved(user) else RedirectResponse("/invite", status_code=303)


@router.get("/history")
def history(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not approved(user):
        return RedirectResponse("/invite", status_code=303)
    return _page("history.html") if profile_done(user) else RedirectResponse("/settings", status_code=303)


@router.get("/admin/invites")
def admin_invites(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page("admin.html") if is_admin(user.email) else RedirectResponse("/", status_code=303)


@router.get("/f")
def feedback_link():
    return _page("f.html")
