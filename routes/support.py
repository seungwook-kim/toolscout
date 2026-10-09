"""고객센터 문의 (2026-10-09 사용자 결정). 로그인 없이도 보낼 수 있다(로그인을 못 하는 사람도 물어야 하니까).

- POST /api/support {email, category, body, website}: 받으면 support_messages에 저장하고 관리자(ADMIN_EMAILS)에게 메일 한 통을 보낸다
  (제목 "[toolscout 문의] 종류", 본문에 문의자 이메일·내용, Reply-To는 문의자 주소). 메일이 실패하거나 관리자 주소가 없어도 DB에는 남고 화면에는 "접수됐어요"
  문의자 주소로는 자동 메일을 절대 보내지 않는다(남의 주소로 스팸을 보내는 통로가 되지 않게). 답장은 관리자가 직접 한다
- 스팸 막기: 클라이언트 HMAC(routes/guard.py)으로 비로그인 1시간 3건, 로그인 1시간 10건(넘으면 429 한국어 안내).
  보이지 않는 꿀단지 칸(website)이 채워지면 저장하지 않고 성공처럼 답한다. 같은 사람이 같은 내용을 바로 또 보내면 한 번만 저장한다
- 관리자만: GET /api/admin/support(최근 문의 목록), POST /api/admin/support/{id}/handled(처리함 표시). 새 문의 수는 승인 탭 배지에 넣지 않는다
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import func, select

import db
from pipeline import deliver
from routes import guard
from routes.auth import EMAIL, base_url, current_user
from routes.invite import require_admin

log = logging.getLogger("toolscout.support")
router = APIRouter()

CATEGORIES = {"account": "계정·로그인", "briefing": "브리핑·메일", "privacy": "개인정보·삭제 요청", "other": "기타"}
BODY_MIN, BODY_MAX, EMAIL_MAX = 10, 2000, 254
HOUR_LIMIT_ANON, HOUR_LIMIT_USER = 3, 10
DUP_WINDOW = timedelta(minutes=10)  # 같은 사람이 같은 내용을 이 안에 또 보내면 거른다
LIST_LIMIT = 50
ACCEPTED = {"ok": True, "message": "접수됐어요. 확인하고 입력하신 이메일로 답장드릴게요"}


class SupportBody(BaseModel):
    email: str = ""
    category: str = ""
    body: str = ""
    website: str = ""  # 꿀단지: 사람 눈에 안 보이는 칸. 채워졌으면 봇이다


def _naive(moment):
    """DB가 돌려주는 시각은 시간대 없는 UTC. 혹시 시간대가 붙어 있으면 떼어서 guard.now()와 비교할 수 있게."""
    return moment.replace(tzinfo=None) if moment.tzinfo else moment


def _notify_admins(message: db.SupportMessage) -> None:
    """관리자에게만 메일 한 통. 실패해도 문의는 DB에 남아 있으니 로그만 남긴다."""
    admins = deliver.admin_emails()
    if not admins:
        log.warning("문의 알림을 받을 ADMIN_EMAILS 없음: 문의 %s", message.id)
        return
    text = (f"고객센터에 문의가 왔어요.\n\n종류: {CATEGORIES[message.category]}\n문의자 이메일: {message.email}\n"
            f"계정 로그인: {'예' if message.user_id else '아니요'}\n\n--- 내용 ---\n{message.body}\n\n"
            f"이 메일에 답장하면 문의자 주소({message.email})로 갑니다. 처리한 뒤에는 관리자 화면에서 [처리함]을 눌러 주세요: {base_url()}/admin/invites")
    try:
        deliver.send_single(admins, f"[toolscout 문의] {CATEGORIES[message.category]}", text, reply_to=message.email)
    except deliver.MailError as exc:
        log.warning("문의 알림 메일 실패(문의 %s는 저장됨): %s", message.id, str(exc).split(":")[0])


@router.post("/api/support")
def send_support(request: Request, payload: SupportBody) -> dict:
    if payload.website.strip():  # 꿀단지: 저장 안 하고 성공처럼 보이게 한다
        return ACCEPTED
    email, body = payload.email.strip(), payload.body.strip()
    if not email or len(email) > EMAIL_MAX or not EMAIL.match(email):
        raise HTTPException(status_code=400, detail="답장 받을 이메일을 올바르게 적어 주세요")
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="문의 종류를 골라 주세요")
    if len(body) < BODY_MIN:
        raise HTTPException(status_code=400, detail=f"내용을 {BODY_MIN}자 이상 적어 주세요")
    if len(body) > BODY_MAX:
        raise HTTPException(status_code=400, detail=f"내용은 {BODY_MAX}자까지 적을 수 있어요")
    user = current_user(request)
    client = guard.client_of(request.headers, request.client.host if request.client else None)
    since = guard.now()
    who = db.SupportMessage.user_id == user.id if user else db.SupportMessage.client_hash == client
    with db.session() as s:
        last = s.exec(select(db.SupportMessage).where(who).order_by(db.SupportMessage.id.desc())).first()
        if last and last.body == body and last.email == email and last.category == payload.category \
                and since - _naive(last.created_at) < DUP_WINDOW:
            return ACCEPTED  # 같은 내용 연속 전송(더블 클릭 등)은 한 번만 저장한다
        used = s.exec(select(func.count()).select_from(db.SupportMessage).where(who, db.SupportMessage.created_at > since - timedelta(hours=1))).one()
        limit = HOUR_LIMIT_USER if user else HOUR_LIMIT_ANON
        if used >= limit:
            raise HTTPException(status_code=429, detail=f"문의를 너무 많이 보냈어요. 1시간에 {limit}건까지 받을 수 있어요. 잠시 뒤에 다시 보내 주세요",
                                headers={"Retry-After": "3600"})
        message = db.SupportMessage(email=email, category=payload.category, body=body, user_id=user.id if user else None, client_hash=client)
        s.add(message)
        s.commit()
        s.refresh(message)
    _notify_admins(message)
    return ACCEPTED


def _row(m: db.SupportMessage) -> dict:
    return {"id": m.id, "email": m.email, "category": m.category, "category_label": CATEGORIES.get(m.category, m.category), "body": m.body,
            "has_account": m.user_id is not None, "created_at": m.created_at.isoformat(),
            "handled_at": m.handled_at.isoformat() if m.handled_at else None}


@router.get("/api/admin/support")
def list_support(admin: db.User = Depends(require_admin)) -> dict:
    """최근 문의 50건(최신순). 처리 안 한 개수는 전체 기준."""
    with db.session() as s:
        rows = s.exec(select(db.SupportMessage).order_by(db.SupportMessage.id.desc()).limit(LIST_LIMIT)).all()
        open_count = s.exec(select(func.count()).select_from(db.SupportMessage).where(db.SupportMessage.handled_at.is_(None))).one()
        return {"messages": [_row(m) for m in rows], "open": open_count}


@router.post("/api/admin/support/{message_id}/handled")
def mark_handled(message_id: int, admin: db.User = Depends(require_admin)) -> dict:
    with db.session() as s:
        message = s.get(db.SupportMessage, message_id)
        if message is None:
            raise HTTPException(status_code=404, detail="없는 문의예요")
        if message.handled_at is None:
            message.handled_at = guard.now()
            s.commit()
            s.refresh(message)
        return _row(message)
