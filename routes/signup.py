"""이메일 회원가입과 비밀번호 로그인 (2026-10-08 사용자 결정: 아이디 = 이메일, 인증번호를 보내 맞으면 가입, 인증번호 확인 버튼,
다음부터는 이메일 + 비밀번호로 로그인, 가입하면 관리자 승인 뒤 사용).

- POST /api/auth/signup/code {email}: 6자리 인증번호를 메일로 보낸다(10분). 같은 주소는 60초에 한 번, 1시간에 5번까지.
  이미 비밀번호로 가입한 주소는 409. 예전 로그인 링크·구글로 만든 계정처럼 비밀번호가 없는 계정은 인증하면 비밀번호를 정해 이어 쓴다.
  개발 모드는 ADMIN_EMAILS 주소만 (개발 모드 실제 발송 예외와 같은 범위)
- POST /api/auth/signup/verify {email, code}: 가장 최근 번호와 맞으면 가입 토큰(30분, 1회용)을 준다. 번호 하나에 5번 틀리면 다시 받아야 한다
- POST /api/auth/signup/complete {signup_token, password}: 비밀번호(8자 이상, 영문과 숫자 섞기)를 정하고 계정을 만든다 → 세션.
  새 계정은 status pending(관리자는 바로 approved), 관리자에게 새 가입 알림 한 통
- POST /api/auth/login {email, password}: 맞으면 세션과 갈 화면. 5번 연속 틀리면 15분 잠금. 없는 주소와 틀린 비밀번호는 같은 말로 답한다
비밀번호는 scrypt(표준 라이브러리), 인증번호는 SESSION_SECRET HMAC으로만 저장한다. 원문은 로그·응답에 쓰지 않는다.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import select

import db
import models
from pipeline import deliver
from routes import tokens
from routes.auth import EMAIL, is_admin, mark_login, next_path, notify_admins_new_user, set_session

router = APIRouter()
CODE_TTL, CODE_TRIES = timedelta(minutes=10), 5
RESEND_GAP, HOURLY_CODES = timedelta(seconds=60), 5
SIGNUP_TTL = 30 * 60
LOGIN_TRIES, LOCK_TIME = 5, timedelta(minutes=15)
PASSWORD_MIN = 8
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1


class CodeBody(BaseModel):
    email: str


class VerifyBody(BaseModel):
    email: str
    code: str


class CompleteBody(BaseModel):
    signup_token: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def check_password(password: str, stored: str | None) -> bool:
    try:
        kind, n, r, p, salt, digest = (stored or "").split("$")
        if kind != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> str | None:
    if len(password) < PASSWORD_MIN:
        return f"비밀번호는 {PASSWORD_MIN}자 이상이어야 해요"
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        return "비밀번호에 영문과 숫자를 섞어 주세요"
    return None


def _code_hash(email: str, code: str) -> str:
    return hmac.new(os.environ.get("SESSION_SECRET", "").encode(), f"signup:{email}:{code}".encode(), hashlib.sha256).hexdigest()


def _email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="이메일 주소를 확인해 주세요")
    return email


def _user(s, email: str) -> db.User | None:
    return s.exec(select(db.User).where(db.User.email == email)).first()


def _aware(moment):
    """DB가 시간대 없는 값을 돌려줄 때(UTC로 저장) 비교할 수 있게."""
    from datetime import timezone

    return moment if moment is None or moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@router.post("/api/auth/signup/code")
def send_code(body: CodeBody) -> dict:
    email = _email(body.email)
    if models.dev_mode() and not is_admin(email):
        raise HTTPException(status_code=403, detail="개발 모드에서는 관리자 이메일만 가입할 수 있어요")
    now = db.utcnow()
    with db.session() as s:
        user = _user(s, email)
        if user is not None and user.password_hash:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일이에요. 로그인해 주세요")
        recent = s.exec(select(db.EmailCode).where(db.EmailCode.email == email, db.EmailCode.created_at > now - timedelta(hours=1))
                        .order_by(db.EmailCode.id.desc())).all()
        if recent and _aware(recent[0].created_at) > now - RESEND_GAP:
            raise HTTPException(status_code=429, detail="방금 보냈어요. 1분 뒤에 다시 받아 주세요")
        if len(recent) >= HOURLY_CODES:
            raise HTTPException(status_code=429, detail="인증번호를 너무 많이 받았어요. 1시간 뒤에 다시 해 주세요")
        code = f"{secrets.randbelow(10**6):06d}"
        text = (f"toolscout 회원가입 인증번호입니다.\n\n인증번호: {code}\n\n10분 안에 가입 화면에 넣어 주세요. "
                "요청하지 않았다면 이 메일은 무시해 주세요.")
        html = (f"<p>toolscout 회원가입 인증번호입니다.</p><p style=\"font-size:24px;letter-spacing:4px\"><b>{code}</b></p>"
                "<p>10분 안에 가입 화면에 넣어 주세요.</p><p style=\"color:#888\">요청하지 않았다면 이 메일은 무시해 주세요.</p>")
        try:
            deliver.send_single([email], "[toolscout] 회원가입 인증번호", text, html)
        except deliver.MailError:
            raise HTTPException(status_code=503, detail="메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요") from None
        s.add(db.EmailCode(email=email, code_hash=_code_hash(email, code), expires_at=now + CODE_TTL))
        s.commit()
    return {"sent": True, "message": "인증번호를 메일로 보냈어요. 10분 안에 넣어 주세요"}


@router.post("/api/auth/signup/verify")
def verify_code(body: VerifyBody) -> dict:
    email, code = _email(body.email), body.code.strip()
    now = db.utcnow()
    with db.session() as s:
        row = s.exec(select(db.EmailCode).where(db.EmailCode.email == email).order_by(db.EmailCode.id.desc())).first()
        if row is None or row.verified_at is not None:
            raise HTTPException(status_code=400, detail="인증번호를 먼저 받아 주세요")
        if _aware(row.expires_at) < now:
            raise HTTPException(status_code=400, detail="인증번호 시간이 지났어요. 다시 받아 주세요")
        if row.attempts >= CODE_TRIES:
            raise HTTPException(status_code=429, detail="여러 번 틀렸어요. 인증번호를 다시 받아 주세요")
        if not hmac.compare_digest(row.code_hash, _code_hash(email, code)):
            row.attempts += 1
            s.commit()
            left = CODE_TRIES - row.attempts
            raise HTTPException(status_code=400 if left else 429,
                                detail=f"인증번호가 맞지 않아요 (남은 횟수 {left})" if left else "여러 번 틀렸어요. 인증번호를 다시 받아 주세요")
        row.verified_at = now
        s.commit()
    return {"verified": True, "signup_token": tokens.sign("signup", {"email": email}, SIGNUP_TTL),
            "message": "인증됐어요. 비밀번호를 정해 주세요"}


@router.post("/api/auth/signup/complete")
def complete(body: CompleteBody) -> JSONResponse:
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    try:
        email = tokens.consume(body.signup_token, "signup")["email"]
    except tokens.TokenError:
        raise HTTPException(status_code=400, detail="인증이 끝났거나 시간이 지났어요. 인증번호를 다시 받아 주세요") from None
    with db.session() as s:
        user = _user(s, email)
        if user is not None and user.password_hash:
            raise HTTPException(status_code=409, detail="이미 가입된 이메일이에요. 로그인해 주세요")
        created = user is None
        if created:
            admin = is_admin(email)
            user = db.User(email=email, role="", is_test=models.dev_mode(), status="approved" if admin else "pending",
                           is_admin=admin, applied_at=db.utcnow())
            s.add(user)
        user.password_hash = hash_password(body.password)
        mark_login(user, "password")  # 가입하면 바로 로그인된다
        s.commit()
        s.refresh(user)
    if created:
        notify_admins_new_user(user, "email")
    return set_session(JSONResponse({"ok": True, "next": next_path(user), "status": user.status,
                                     "message": "가입됐어요" if user.status == "approved" else "가입 신청이 됐어요. 관리자 승인 뒤 브리핑이 시작돼요"}), user)


@router.post("/api/auth/login")
def login(body: LoginBody) -> JSONResponse:
    email = body.email.strip().lower()
    wrong = HTTPException(status_code=400, detail="이메일 또는 비밀번호가 맞지 않아요")
    now = db.utcnow()
    with db.session() as s:
        user = _user(s, email) if EMAIL.match(email) else None
        if user is None or not user.password_hash:
            raise wrong
        if user.login_locked_until and _aware(user.login_locked_until) > now:
            raise HTTPException(status_code=429, detail="로그인 시도가 너무 많아요. 15분 뒤에 다시 해 주세요")
        if not check_password(body.password, user.password_hash):
            user.login_failures += 1
            if user.login_failures >= LOGIN_TRIES:
                user.login_failures, user.login_locked_until = 0, now + LOCK_TIME
            s.commit()
            raise wrong
        user.login_failures, user.login_locked_until = 0, None
        if models.dev_mode():
            user.is_test = True
        mark_login(user, "password")
        s.commit()
        s.refresh(user)
    return set_session(JSONResponse({"ok": True, "next": next_path(user), "status": user.status}), user)
