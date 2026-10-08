"""세션과 공통 로그인 도우미 (계획안 9.3 routes). 회원가입·비밀번호 로그인은 routes/signup.py, 구글 로그인은 routes/google.py.

2026-10-08 사용자 결정: 첫 화면은 회원가입 + 구글 로그인 중 하나, 아이디 = 이메일, 인증번호 확인 뒤 가입, 가입하지 않는 사람은
데모(고정 예시)만. 가입하면 관리자 승인 뒤 브리핑을 받는다(초대 코드·이용 신청서는 뺐다). 예전 이메일 로그인 링크 요청도 뺐다.
- GET /auth/verify?token=: 서명 로그인 토큰(purpose login, 1회용)으로 세션을 만든다. 화면에서는 쓰지 않고 검수·관리 도구용
  (토큰은 SESSION_SECRET이 있어야 만들 수 있다). 사용자가 없으면 만든다(status pending)
- GET /api/auth/options: 구글 로그인을 쓸 수 있는지 (GOOGLE_CLIENT_ID·SECRET)
- POST /api/auth/logout, GET /api/me
세션 쿠키 ts_session: 서명 토큰(30일), HttpOnly, SameSite=Lax. 모든 API는 세션이 필요하다 (메일 피드백 링크·공개 데모 제외).
로그인은 누구나 하지만 status가 pending·blocked면 승인 대기 화면(/pending)만 보이고
브리핑·질문·피드백·설정 API는 403이다 (require_approved). 개발 모드에서는 로그인한 사용자를 is_test=True로 둔다.
"""
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlmodel import func, select

import db
import models
from pipeline import deliver
from routes import tokens

SESSION_COOKIE = "ts_session"
SESSION_TTL = 30 * 24 * 3600
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter()


def base_url() -> str:
    return os.environ.get("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def is_admin(email: str | None) -> bool:
    return bool(email) and email.lower() in {e.lower() for e in deliver.admin_emails()}


def current_user(request: Request) -> db.User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        data = tokens.verify(token, "session")
    except tokens.TokenError:
        return None
    with db.session() as s:
        return s.get(db.User, data.get("uid"))


def require_user(request: Request) -> db.User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="로그인이 필요해요")
    return user


def approved(user: db.User) -> bool:
    return user.status == "approved"


def require_approved(request: Request) -> db.User:
    """세션 + 승인된 사용자. 승인 전이거나 차단된 사용자는 403."""
    user = require_user(request)
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="이 계정은 사용할 수 없어요")
    if not approved(user):
        raise HTTPException(status_code=403, detail="관리자 승인을 기다리고 있어요")
    return user


def profile_done(user: db.User) -> bool:
    return bool((user.role or "").strip())


def next_path(user: db.User) -> str:
    """로그인 뒤 갈 화면: 승인 전이면 승인 대기, 프로필이 비었으면 설정, 아니면 오늘 브리핑."""
    if not approved(user):
        return "/pending"
    return "/" if profile_done(user) else "/settings"


def set_session(response: Response, user: db.User) -> Response:
    response.set_cookie(SESSION_COOKIE, tokens.sign("session", {"uid": user.id}, SESSION_TTL), max_age=SESSION_TTL,
                        httponly=True, samesite="lax", secure=base_url().startswith("https://"))
    return response


def mark_login(user: db.User, method: str) -> None:
    """로그인에 성공했을 때 마지막 로그인 시각·방법을 적는다(커밋은 부르는 쪽). 관리자 사용자 목록에 보인다 (2026-10-09 사용자 결정 (가))."""
    user.last_login_at, user.last_login_method = db.utcnow(), method


def login_response(user: db.User, target: str) -> RedirectResponse:
    return set_session(RedirectResponse(target, status_code=303), user)


def notify_admins_new_user(user: db.User, via: str) -> None:
    """새 가입 신청을 관리자에게 알린다(승인해야 쓰므로). 관리자 본인 가입이거나 메일이 안 가도 가입은 막지 않는다."""
    admins = deliver.admin_emails()
    if not admins or is_admin(user.email):
        return
    text = (f"새 가입 신청이 있어요 ({'구글' if via == 'google' else '이메일'}).\n\n{user.email}\n\n"
            f"승인: {base_url()}/admin/invites")
    try:
        deliver.send_single(admins, "[toolscout] 새 가입 신청", text)
    except deliver.MailError:
        pass


@router.get("/auth/verify", include_in_schema=False)
def verify_link(token: str = "") -> RedirectResponse:
    try:
        data = tokens.consume(token, "login")
    except tokens.TokenError as exc:
        return RedirectResponse(f"/login?error={exc.reason}", status_code=303)
    email = data["email"]
    with db.session() as s:
        user = s.exec(select(db.User).where(db.User.email == email)).first()
        if user is None:
            user = db.User(email=email, role="", is_test=models.dev_mode())
            s.add(user)
        if models.dev_mode():
            user.is_test = True  # 개발 모드: 로그인한 사용자도 브리핑 대상(is_test)에 넣는다
        mark_login(user, "link")
        s.commit()
        s.refresh(user)
    return login_response(user, next_path(user))


def google_ready() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID", "").strip() and os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())


@router.get("/api/auth/options")
def options() -> dict:
    return {"google": google_ready(), "dev_mode": models.dev_mode()}


@router.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


def pending_applications() -> int:
    """승인을 기다리는 가입 수 (관리자 메뉴의 "승인" 탭 숫자)."""
    with db.session() as s:
        return s.exec(select(func.count()).select_from(db.User).where(db.User.status == "pending", db.User.is_demo == False)).one()  # noqa: E712


@router.get("/api/me")
def me(user: db.User = Depends(require_user)) -> dict:
    admin = is_admin(user.email)
    return {"id": user.id, "email": user.email, "role": user.role, "profile_done": profile_done(user),
            "is_admin": admin, "dev_mode": models.dev_mode(), "status": user.status,
            "approved": approved(user), "pending_applications": pending_applications() if admin else 0,
            "login": "google" if user.google_sub else ("password" if user.password_hash else "link")}
