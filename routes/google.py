"""구글 로그인 (2026-10-08 사용자 결정 "회원가입 버튼 + 구글 로그인 2중 선택1"). OAuth 2.0 인가 코드 방식, 새 라이브러리 없이 httpx로.

- GET /auth/google: 구글 동의 화면으로 보낸다. state는 서명 토큰(10분)이고 같은 값을 쿠키(ts_oauth)에도 넣어 콜백에서 맞춘다
- GET /auth/google/callback?code=&state=: 코드를 토큰으로 바꾸고 id_token을 구글 tokeninfo로 확인한다
  (aud = 우리 클라이언트 ID, 발급자 accounts.google.com, 이메일 확인됨). google_sub로 찾고, 없으면 같은 이메일 계정에 붙이고
  (구글이 확인한 주소라서), 없으면 새로 만든다(status pending, 관리자는 approved, 관리자에게 새 가입 알림) → 세션 → 갈 화면
- GOOGLE_CLIENT_ID·GOOGLE_CLIENT_SECRET이 없으면 /auth/google은 /login?error=google_off (화면은 /api/auth/options로 버튼을 숨긴다)
- 개발 모드는 ADMIN_EMAILS 주소만 (/login?error=dev_only)
- Gmail 발송 연결(2026-10-09, 관리자 전용, 한 번만): GET /admin/gmail/connect가 gmail.send 권한을 offline으로 요청한다. 구글 콘솔에 등록된
  리디렉션 주소는 위 콜백 하나뿐이라 같은 콜백을 쓰고, state 안의 종류 k="gmail"이면 로그인이 아니라 연결로 처리한다. 코드 -> 토큰 교환 ->
  id_token의 이메일이 GMAIL_USER와 같을 때만 refresh_token을 암호화해 저장하고 /admin/invites?gmail=결과로 돌아간다
  (결과: connected / no_refresh / wrong_account / failed). GET /api/admin/gmail은 연결 상태(관리자 전용)
구글 클라우드 콘솔에 등록할 리디렉션 주소: {APP_BASE_URL}/auth/google/callback. 토큰·코드 원문은 로그에 쓰지 않는다.
"""
import hmac
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select

import db
import models
from pipeline import deliver, gmail_api
from routes import tokens
from routes.auth import (base_url, current_user, google_ready, is_admin, login_response, mark_login, next_path,
                         notify_admins_new_user)
from routes.invite import require_admin

router = APIRouter(include_in_schema=False)
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send openid email"
STATE_COOKIE, STATE_TTL = "ts_oauth", 600
_post, _get = httpx.post, httpx.get  # 검수에서 가짜 구글로 바꿔 끼운다


def _redirect_uri() -> str:
    return f"{base_url()}/auth/google/callback"


def _fail(reason: str) -> RedirectResponse:
    response = RedirectResponse(f"/login?error={reason}", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/auth/google")
def start() -> RedirectResponse:
    if not google_ready():
        return _fail("google_off")
    state = tokens.sign("google_state", {"r": secrets.token_hex(8)}, STATE_TTL)
    query = urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"].strip(), "redirect_uri": _redirect_uri(), "response_type": "code",
                       "scope": "openid email profile", "state": state, "prompt": "select_account"})
    response = RedirectResponse(f"{AUTH_URL}?{query}", status_code=303)
    response.set_cookie(STATE_COOKIE, state, max_age=STATE_TTL, httponly=True, samesite="lax", secure=base_url().startswith("https://"))
    return response


def _exchange(code: str) -> tuple[dict, dict] | None:
    """인가 코드 → (토큰 응답, 확인된 id_token 내용). aud·발급자·이메일 확인까지 맞아야 하고, 아니면 None."""
    client_id = os.environ["GOOGLE_CLIENT_ID"].strip()
    try:
        token = _post(TOKEN_URL, data={"code": code, "client_id": client_id, "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
                                       "redirect_uri": _redirect_uri(), "grant_type": "authorization_code"}, timeout=15)
        body = token.json() if token.status_code == 200 else {}
        id_token = body.get("id_token")
        if not id_token:
            return None
        info = _get(TOKENINFO_URL, params={"id_token": id_token}, timeout=15)
        claims = info.json() if info.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return None
    if claims.get("aud") != client_id or claims.get("iss") not in ISSUERS or str(claims.get("email_verified")).lower() != "true":
        return None
    return body, claims


def _identity(code: str) -> dict | None:
    """인가 코드 → 확인된 구글 계정 {sub, email}. 실패면 None."""
    got = _exchange(code)
    if got is None:
        return None
    claims = got[1]
    email, sub = (claims.get("email") or "").strip().lower(), str(claims.get("sub") or "")
    return {"sub": sub, "email": email} if email and sub else None


def _gmail_done(result: str) -> RedirectResponse:
    response = RedirectResponse(f"/admin/invites?gmail={result}", status_code=303)
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/admin/gmail/connect")
def gmail_connect(request: Request) -> RedirectResponse:
    """관리자만. 구글 동의 화면으로 보낸다 (gmail.send, offline, 항상 동의 화면을 거쳐 refresh_token을 받는다)."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if not is_admin(user.email):
        raise HTTPException(status_code=403, detail="관리자만 쓸 수 있어요")
    if not google_ready():
        return _gmail_done("failed")
    state = tokens.sign("google_state", {"r": secrets.token_hex(8), "k": "gmail"}, STATE_TTL)
    query = {"client_id": os.environ["GOOGLE_CLIENT_ID"].strip(), "redirect_uri": _redirect_uri(), "response_type": "code",
             "scope": GMAIL_SCOPE, "state": state, "access_type": "offline", "prompt": "consent"}
    sender = os.environ.get("GMAIL_USER", "").strip()
    if sender:
        query["login_hint"] = sender
    response = RedirectResponse(f"{AUTH_URL}?{urlencode(query)}", status_code=303)
    response.set_cookie(STATE_COOKIE, state, max_age=STATE_TTL, httponly=True, samesite="lax", secure=base_url().startswith("https://"))
    return response


def _gmail_finish(request: Request, code: str) -> RedirectResponse:
    """연결 흐름의 콜백. 관리자 세션이 그대로 있어야 하고, 로그인한 계정이 아니라 동의한 구글 계정이 GMAIL_USER여야 저장한다."""
    user = current_user(request)
    if user is None or not is_admin(user.email):
        return _fail("google_failed")
    got = _exchange(code)
    if got is None:
        return _gmail_done("failed")
    body, claims = got
    sender = os.environ.get("GMAIL_USER", "").strip().lower()
    if not sender or (claims.get("email") or "").strip().lower() != sender:
        return _gmail_done("wrong_account")  # 다른 계정이면 저장하지 않는다
    if "gmail.send" not in str(body.get("scope", "gmail.send")):
        return _gmail_done("failed")
    refresh = body.get("refresh_token")
    if not refresh:
        return _gmail_done("no_refresh")  # 이미 동의한 계정이면 구글이 다시 주지 않는다
    gmail_api.save_refresh_token(refresh)
    return _gmail_done("connected")


@router.get("/api/admin/gmail")
def gmail_status(admin: db.User = Depends(require_admin)) -> dict:
    """연결 상태 (관리자 전용). 토큰 값은 내보내지 않는다."""
    return {**gmail_api.connection_status(), "transport": deliver.transport(), "sender_set": bool(os.environ.get("GMAIL_USER", "").strip()),
            "google_ready": google_ready()}


@router.get("/auth/google/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    if not google_ready():
        return _fail("google_off")
    cookie = request.cookies.get(STATE_COOKIE, "")
    if error or not code or not state or not hmac.compare_digest(cookie, state):
        return _fail("google_failed")
    try:
        kind = tokens.verify(state, "google_state").get("k")
    except tokens.TokenError:
        return _fail("google_failed")
    if kind == "gmail":  # 로그인이 아니라 Gmail 발송 연결
        return _gmail_finish(request, code)
    identity = _identity(code)
    if identity is None:
        return _fail("google_failed")
    if models.dev_mode() and not is_admin(identity["email"]):
        return _fail("dev_only")
    with db.session() as s:
        user = s.exec(select(db.User).where(db.User.google_sub == identity["sub"])).first()
        user = user or s.exec(select(db.User).where(db.User.email == identity["email"])).first()
        created = user is None
        if created:
            admin = is_admin(identity["email"])
            user = db.User(email=identity["email"], role="", status="approved" if admin else "pending", is_admin=admin,
                           applied_at=db.utcnow())
            s.add(user)
        if user.status == "blocked":
            return _fail("blocked")
        user.google_sub = identity["sub"]
        user.is_test = user.is_test or models.dev_mode()
        mark_login(user, "google")
        s.commit()
        s.refresh(user)
    if created:
        notify_admins_new_user(user, "google")
    response = login_response(user, next_path(user))
    response.delete_cookie(STATE_COOKIE)
    return response
