"""로그인 (이메일 매직링크)과 세션 (계획안 6장 "이메일 직접 입력", 9.3 routes). 카카오 로그인은 나중에 이 파일에 붙인다.

- POST /api/auth/request {email}: 서명 링크(15분, 1회용)를 메일로 보낸다
  개발 모드는 ADMIN_EMAILS 주소만 받는다 (개발 모드 실제 발송 예외와 같은 범위)
- GET /auth/verify?token=: 링크 확인 → 사용자가 없으면 만든다 → 세션 쿠키 → 프로필이 비었으면 /settings, 아니면 /
  개발 모드에서는 로그인한 사용자를 is_test=True로 둬서 브리핑 대상에 넣는다
- POST /api/auth/logout, GET /api/me
세션 쿠키 ts_session: 서명 토큰(30일), HttpOnly, SameSite=Lax. 모든 API는 세션이 필요하다 (메일 피드백 링크 제외).
"""
import os
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

import db
import models
from pipeline import deliver
from routes import tokens

SESSION_COOKIE = "ts_session"
SESSION_TTL = 30 * 24 * 3600
LOGIN_TTL = 15 * 60
RESEND_SECONDS = 60
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_last_request: dict[str, float] = {}

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


def profile_done(user: db.User) -> bool:
    return bool((user.role or "").strip())


class LoginRequest(BaseModel):
    email: str


@router.post("/api/auth/request")
def request_link(body: LoginRequest) -> dict:
    email = body.email.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="이메일 주소를 확인해 주세요")
    if models.dev_mode() and not is_admin(email):
        raise HTTPException(status_code=403, detail="개발 모드에서는 관리자 이메일만 로그인 링크를 받을 수 있어요")
    now = time.monotonic()
    if now - _last_request.get(email, -RESEND_SECONDS) < RESEND_SECONDS:
        raise HTTPException(status_code=429, detail="방금 보냈어요. 1분 뒤에 다시 요청해 주세요")
    token = tokens.sign("login", {"email": email}, LOGIN_TTL)
    link = f"{base_url()}/auth/verify?token={quote(token)}"
    text = f"toolscout 로그인 링크입니다. 15분 안에 한 번만 쓸 수 있어요.\n\n{link}\n\n요청하지 않았다면 이 메일은 무시해 주세요."
    html = (f'<p>toolscout 로그인 링크입니다. 15분 안에 한 번만 쓸 수 있어요.</p><p><a href="{link}">로그인하기</a></p>'
            "<p style=\"color:#888\">요청하지 않았다면 이 메일은 무시해 주세요.</p>")
    try:
        deliver.send_single([email], "[toolscout] 로그인 링크", text, html)
    except deliver.MailError:
        raise HTTPException(status_code=503, detail="메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요") from None
    _last_request[email] = now
    return {"sent": True, "message": "메일로 로그인 링크를 보냈어요. 15분 안에 눌러 주세요"}


def login_response(user: db.User, target: str) -> RedirectResponse:
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(SESSION_COOKIE, tokens.sign("session", {"uid": user.id}, SESSION_TTL), max_age=SESSION_TTL,
                        httponly=True, samesite="lax", secure=base_url().startswith("https://"))
    return response


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
        s.commit()
        s.refresh(user)
    return login_response(user, "/" if profile_done(user) else "/settings")


@router.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/api/me")
def me(user: db.User = Depends(require_user)) -> dict:
    return {"id": user.id, "email": user.email, "role": user.role, "profile_done": profile_done(user),
            "is_admin": is_admin(user.email), "dev_mode": models.dev_mode()}
