"""초대제 가입 (계획안 7장 사용자 흐름, 2026-09-16 사용자 결정). 로그인은 누구나 하지만 코드를 넣어야 승인된다.

- POST /api/invite/redeem {code}: 유효하면 status=approved, invite_code_used 기록, 코드 used +1
  틀림·만료·횟수 초과는 400. 같은 사용자가 1분에 10번까지만 시도할 수 있다
- 관리자(ADMIN_EMAILS)만: GET·POST /api/admin/invites(코드 목록·생성), GET /api/admin/users(대기·차단 목록),
  POST /api/admin/users/{id}/status(승인·차단·되돌리기)
코드 값은 로그에 쓰지 않는다.
"""
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import select

import db
from routes.auth import is_admin, require_user

router = APIRouter()
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 헷갈리는 글자(I·O·0·1) 제외
CODE_LENGTH = 8
TRY_WINDOW, TRY_LIMIT = 60.0, 10
STATUSES = ("pending", "approved", "blocked")
_tries: dict[int, list[float]] = {}


class RedeemBody(BaseModel):
    code: str


class NewCode(BaseModel):
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_days: int | None = Field(default=30, ge=1, le=365)


class StatusBody(BaseModel):
    status: str


def require_admin(request: Request) -> db.User:
    user = require_user(request)
    if not is_admin(user.email):
        raise HTTPException(status_code=403, detail="관리자만 쓸 수 있어요")
    return user


def _too_many(user_id: int) -> bool:
    now = time.monotonic()
    tries = [t for t in _tries.get(user_id, []) if now - t < TRY_WINDOW]
    _tries[user_id] = tries + [now]
    return len(tries) >= TRY_LIMIT


def _valid(code: db.InviteCode) -> str | None:
    """못 쓰는 이유. 쓸 수 있으면 None."""
    if code.expires_at and code.expires_at.replace(tzinfo=code.expires_at.tzinfo or timezone.utc) < db.utcnow():
        return "기한이 지난 코드예요"
    if code.used >= code.max_uses:
        return "이미 다 쓴 코드예요"
    return None


@router.post("/api/invite/redeem")
def redeem(body: RedeemBody, user: db.User = Depends(require_user)) -> dict:
    if user.status == "blocked":
        raise HTTPException(status_code=403, detail="이 계정은 사용할 수 없어요")
    if user.status == "approved":
        return {"status": "approved", "message": "이미 가입되어 있어요"}
    if _too_many(user.id):
        raise HTTPException(status_code=429, detail="시도가 너무 많아요. 1분 뒤에 다시 해 주세요")
    value = body.code.strip().upper()
    with db.session() as s:
        code = s.exec(select(db.InviteCode).where(db.InviteCode.code == value)).first()
        if code is None:
            raise HTTPException(status_code=400, detail="없는 코드예요")
        problem = _valid(code)
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        code.used += 1
        member = s.get(db.User, user.id)
        member.status, member.invite_code_used = "approved", value
        s.commit()
    return {"status": "approved", "message": "가입됐어요. 내일 아침 첫 브리핑이 갑니다"}


@router.get("/api/admin/invites")
def list_codes(admin: db.User = Depends(require_admin)) -> dict:
    with db.session() as s:
        codes = s.exec(select(db.InviteCode).order_by(db.InviteCode.id.desc())).all()
        return {"codes": [{"code": c.code, "max_uses": c.max_uses, "used": c.used,
                           "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                           "left": max(c.max_uses - c.used, 0), "unusable": _valid(c)} for c in codes]}


@router.post("/api/admin/invites")
def create_code(body: NewCode, admin: db.User = Depends(require_admin)) -> dict:
    value = "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))
    expires = datetime.now(timezone.utc) + timedelta(days=body.expires_days) if body.expires_days else None
    with db.session() as s:
        s.add(db.InviteCode(code=value, max_uses=body.max_uses, expires_at=expires, created_by=admin.id))
        s.commit()
    return {"code": value, "max_uses": body.max_uses, "expires_at": expires.isoformat() if expires else None}


@router.get("/api/admin/users")
def list_users(admin: db.User = Depends(require_admin)) -> dict:
    with db.session() as s:
        users = s.exec(select(db.User).order_by(db.User.id)).all()
        return {"users": [{"id": u.id, "email": u.email, "role": u.role, "status": u.status, "is_test": u.is_test,
                           "is_demo": u.is_demo, "invite_code_used": u.invite_code_used,
                           "created_at": u.created_at.isoformat()} for u in users]}


@router.post("/api/admin/users/{user_id}/status")
def set_status(user_id: int, body: StatusBody, admin: db.User = Depends(require_admin)) -> dict:
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="status는 pending·approved·blocked만 돼요")
    with db.session() as s:
        member = s.get(db.User, user_id)
        if member is None:
            raise HTTPException(status_code=404, detail="없는 사용자예요")
        member.status = body.status
        s.commit()
    return {"id": user_id, "status": body.status}
