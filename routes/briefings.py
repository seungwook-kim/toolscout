"""브리핑 조회 API (계획안 9.3 "브리핑 API", F8 지난 브리핑). 모두 세션 필요, 본인 브리핑만.

- GET /api/briefings/today, GET /api/briefings?date=: 그날 카드(카드 JSON + 내 피드백 상태), "N건 중 M건", 기준 한 줄, empty_reason
  관리자(ADMIN_EMAILS)에게만 카드마다 Langfuse 트레이스 주소
- GET /api/briefings/dates: 내 브리핑이 있는 날짜 목록
- GET /api/search?q=: 내 브리핑에 나왔던 항목의 제목·이름 키워드 검색 (DB LIKE, LLM 없음)
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select

import db
from agent import tracing
from agent.schemas import TOPICS
from pipeline.run_daily import today_kst
from routes.auth import is_admin, require_user

router = APIRouter()
SEARCH_LIMIT = 30


def profile_line(user: db.User) -> str:
    parts = [user.role or "직군 미설정"]
    if user.profile_tools_tags:
        parts.append(", ".join(user.profile_tools_tags[:5]))
    if user.profile_free_text:
        parts.append(user.profile_free_text)
    return " · ".join(parts)


def feedback_state(user_id: int, item_ids: list[int]) -> dict[int, dict]:
    if not item_ids:
        return {}
    state: dict[int, dict] = {}
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Feedback.item_id, db.Feedback.action, db.Feedback.reason, db.Feedback.memo, db.Feedback.id)
                            .where(db.Feedback.user_id == user_id, db.Feedback.item_id.in_(item_ids)).order_by(db.Feedback.id))
        for item_id, action, reason, memo, feedback_id in rows:
            entry = state.setdefault(item_id, {"actions": [], "reason": None, "memo": None, "ids": {}})
            entry["actions"].append(action)
            entry["ids"][action] = feedback_id
            entry["reason"] = reason or entry["reason"]
            entry["memo"] = memo or entry["memo"]
    return state


def briefing_for(user: db.User, day: date) -> dict:
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Briefing.item_id, db.Briefing.rank, db.Briefing.card_json, db.Briefing.empty_reason,
                                   db.Briefing.pool_size, db.Briefing.trace_id, db.Briefing.sent_at, db.Item.topic)
                            .outerjoin(db.Item, db.Item.id == db.Briefing.item_id)
                            .where(db.Briefing.user_id == user.id, db.Briefing.date == day).order_by(db.Briefing.rank)).all()
    admin = is_admin(user.email)
    cards, empty_reason, pool_size = [], None, None
    state = feedback_state(user.id, [r.item_id for r in rows if r.item_id])
    for row in rows:
        pool_size = row.pool_size or pool_size
        if row.card_json is None:
            empty_reason = row.empty_reason
            continue
        card = dict(row.card_json) | {"item_id": row.item_id, "topic": row.topic, "topic_label": TOPICS.get(row.topic or "", ""),
                                      "feedback": state.get(row.item_id, {"actions": [], "reason": None, "memo": None, "ids": {}})}
        if admin:
            card["trace_url"] = tracing.trace_url(row.trace_id) or f"trace_id {row.trace_id}"
        cards.append(card)
    return {"date": str(day), "profile_line": profile_line(user), "pool_size": pool_size, "count": len(cards),
            "cards": cards, "empty_reason": empty_reason, "exists": bool(rows), "is_admin": admin,
            "sent": any(r.sent_at for r in rows)}


@router.get("/api/briefings/today")
def today(user: db.User = Depends(require_user)) -> dict:
    return briefing_for(user, today_kst())


@router.get("/api/briefings")
def by_date(day: date = Query(alias="date"), user: db.User = Depends(require_user)) -> dict:
    return briefing_for(user, day)


@router.get("/api/briefings/dates")
def dates(user: db.User = Depends(require_user)) -> dict:
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Briefing.date, func.count(db.Briefing.item_id))
                            .where(db.Briefing.user_id == user.id).group_by(db.Briefing.date)
                            .order_by(db.Briefing.date.desc())).all()
    return {"dates": [{"date": str(d), "cards": n} for d, n in rows]}


@router.get("/api/search")
def search(q: str = "", user: db.User = Depends(require_user)) -> dict:
    words = [w for w in q.split() if len(w) >= 2][:5]
    if not words:
        raise HTTPException(status_code=400, detail="두 글자 이상으로 검색해 주세요")
    conditions = [or_(db.Item.title.ilike(f"%{w}%"), db.Item.summary_ko.ilike(f"%{w}%")) for w in words]
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Briefing.date, db.Item.id, db.Item.title, db.Item.url, db.Item.type, db.Item.summary_ko)
                            .join(db.Item, db.Item.id == db.Briefing.item_id)
                            .where(db.Briefing.user_id == user.id, *conditions)
                            .order_by(db.Briefing.date.desc()).limit(SEARCH_LIMIT)).all()
    return {"q": q, "results": [{"date": str(r.date), "item_id": r.id, "title": r.title, "url": r.url, "type": r.type,
                                 "summary_ko": r.summary_ko} for r in rows]}
