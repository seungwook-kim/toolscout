"""가입 승인과 사용자 관리 (관리자 전용). 2026-10-08 사용자 결정: 가입은 이메일(인증번호)·구글로 누구나 하고, 관리자가 승인해야
브리핑을 받는다. 예전 초대 코드 입력·이용 신청서는 뺐다(invite_codes 표와 users.application 칸은 기록으로 남는다).

- 관리자(ADMIN_EMAILS)만: GET /api/admin/applications(승인 대기 가입: 먼저 가입한 순서, 가입 방법),
  GET /api/admin/users(전체 사용자와 마지막 결정, 마지막 로그인 시각·방법), POST /api/admin/users/{id}/status(승인·차단·되돌리기),
  GET /api/admin/status-changes(최근 상태 변경 이력: 누가·누구를·무엇에서 무엇으로·언제·어떻게)
- 상태가 실제로 바뀔 때마다 status_changes에 한 줄 남긴다. 같은 상태로 누르면 남기지 않는다
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

import db
from routes.auth import is_admin, require_user

router = APIRouter()
STATUSES = ("pending", "approved", "blocked")
HISTORY_LIMIT = 50


class StatusBody(BaseModel):
    status: str


def require_admin(request: Request) -> db.User:
    user = require_user(request)
    if not is_admin(user.email):
        raise HTTPException(status_code=403, detail="관리자만 쓸 수 있어요")
    return user


def _record(s, member: db.User, new: str, via: str, by: int | None) -> None:
    """상태가 실제로 바뀔 때만 이력을 남기고 바꾼다 (같은 세션에서 커밋)."""
    if member.status == new:
        return
    s.add(db.StatusChange(user_id=member.id, old_status=member.status, new_status=new, changed_by=by, via=via))
    member.status = new


def signup_via(user: db.User) -> str:
    return "google" if user.google_sub else ("email" if user.password_hash else "link")


@router.get("/api/admin/applications")
def list_applications(admin: db.User = Depends(require_admin)) -> dict:
    """승인 대기(pending) 가입. 먼저 가입한 순서. 데모 프로필은 뺀다."""
    with db.session() as s:
        users = s.exec(select(db.User).where(db.User.status == "pending", db.User.is_demo == False)  # noqa: E712
                       .order_by(db.User.created_at)).all()
        return {"applications": [{"id": u.id, "email": u.email, "via": signup_via(u), "applied_at": (u.applied_at or u.created_at).isoformat()}
                                 for u in users]}


def _history(s, limit: int | None = HISTORY_LIMIT) -> list[dict]:
    """최근 순. 주소는 관리자 화면에만 나간다."""
    query = select(db.StatusChange).order_by(db.StatusChange.changed_at.desc(), db.StatusChange.id.desc())
    changes = s.exec(query.limit(limit) if limit else query).all()
    ids = {c.user_id for c in changes} | {c.changed_by for c in changes if c.changed_by}
    emails = {u.id: u.email for u in s.exec(select(db.User).where(db.User.id.in_(ids))).all()} if ids else {}
    return [{"user_id": c.user_id, "email": emails.get(c.user_id), "old": c.old_status, "new": c.new_status, "via": c.via,
             "by": emails.get(c.changed_by) if c.changed_by else None, "at": c.changed_at.isoformat()} for c in changes]


@router.get("/api/admin/status-changes")
def status_changes(admin: db.User = Depends(require_admin)) -> dict:
    with db.session() as s:
        return {"changes": _history(s)}


@router.get("/api/admin/users")
def list_users(admin: db.User = Depends(require_admin)) -> dict:
    with db.session() as s:
        last = {}
        for change in _history(s, None):  # 사용자마다 가장 최근 결정 하나
            last.setdefault(change["user_id"], change)
        users = s.exec(select(db.User).order_by(db.User.id)).all()
        return {"users": [{"id": u.id, "email": u.email, "role": u.role, "status": u.status, "is_test": u.is_test,
                           "is_demo": u.is_demo, "via": signup_via(u), "last_change": last.get(u.id),
                           "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                           "last_login_method": u.last_login_method, "created_at": u.created_at.isoformat()} for u in users]}


@router.post("/api/admin/users/{user_id}/status")
def set_status(user_id: int, body: StatusBody, admin: db.User = Depends(require_admin)) -> dict:
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="status는 pending·approved·blocked만 돼요")
    with db.session() as s:
        member = s.get(db.User, user_id)
        if member is None:
            raise HTTPException(status_code=404, detail="없는 사용자예요")
        _record(s, member, body.status, "admin", admin.id)
        s.commit()
    return {"id": user_id, "status": body.status}
