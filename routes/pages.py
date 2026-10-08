"""웹앱 화면 (계획안 9.3 "/는 화면"). 정적 HTML을 돌려주고 데이터는 화면의 JS가 /api/로 가져온다.

- /login: 첫 화면(2026-10-08 사용자 결정). 이메일·비밀번호 로그인, 회원가입 버튼, 구글 로그인, 가입 없이 데모 보기
- /signup: 이메일(아이디) → 인증번호 받기 → 인증번호 확인 → 비밀번호 정하고 가입 / /pending: 관리자 승인 대기
- /: 오늘 브리핑 / /settings: 프로필·설정 / /history: 지난 브리핑 / /f: 메일 피드백 링크 결과 / /admin/invites: 관리자 가입 승인·사용자 관리
- /onboarding: 첫 설정(2026-10-09 리디자인). 승인됐고 프로필(직군)이 비면 /settings 대신 이 화면. 프로필이 차 있으면 /로 보낸다
- 로그인이 필요한 화면은 세션이 없으면 /login으로, 승인 전이면 /pending으로, 프로필이 비었으면 /onboarding으로 보낸다.
  예전 초대 코드 화면 주소 /invite는 /pending으로 보낸다
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


def _gate(request: Request, page: str, need_profile: bool = True):
    """로그인·승인·프로필을 확인해 화면이나 갈 곳을 돌려준다."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not approved(user):
        return RedirectResponse("/pending", status_code=303)
    if need_profile and not profile_done(user):
        return RedirectResponse("/onboarding", status_code=303)
    return _page(page)


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    return PlainTextResponse(ROBOTS)


@router.get("/")
def today(request: Request):
    return _gate(request, "index.html")


@router.get("/login")
def login(request: Request):
    return RedirectResponse("/", status_code=303) if current_user(request) else _page("login.html")


@router.get("/signup")
def signup(request: Request):
    return RedirectResponse("/", status_code=303) if current_user(request) else _page("signup.html")


@router.get("/pending")
def pending(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/", status_code=303) if approved(user) else _page("pending.html")


@router.get("/invite")
def invite():
    return RedirectResponse("/pending", status_code=303)


@router.get("/settings")
def settings(request: Request):
    return _gate(request, "settings.html")


@router.get("/onboarding")
def onboarding(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not approved(user):
        return RedirectResponse("/pending", status_code=303)
    return RedirectResponse("/", status_code=303) if profile_done(user) else _page("onboarding.html")


@router.get("/history")
def history(request: Request):
    return _gate(request, "history.html")


@router.get("/admin/invites")
def admin_invites(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page("admin.html") if is_admin(user.email) else RedirectResponse("/", status_code=303)


@router.get("/f")
def feedback_link():
    return _page("f.html")
