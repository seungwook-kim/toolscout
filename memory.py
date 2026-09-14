"""두 층 기억 읽기 (계획안 5장 기억 설계). 쓰기·합치기·잊기는 피드백 단계에서 붙인다.

- 전체 기억: 프로필(직군·쓰는 도구·자유 한 줄), 주제 가중치, 써봤음 항목
- 일일 기억: 오늘 보여준 항목, 오늘 질문 횟수
검색도 임베딩도 없다. 기사 본문·다른 사용자 정보·검증 로그는 넣지 않는다.
"""
from datetime import date, datetime, time, timezone

from sqlmodel import func, select

import db


def read(user_id: int, today: date | None = None) -> dict:
    """사용자 기억. 사용자가 없으면 {"found": False}."""
    today = today or date.today()
    start = datetime.combine(today, time.min)
    with db.session() as s:
        user = s.get(db.User, user_id)
        if user is None:
            return {"user_id": user_id, "found": False}
        weights = {w.topic: w.weight for w in s.exec(select(db.Weight).where(db.Weight.user_id == user_id))}
        seen = s.exec(select(db.Item.url, db.Seen.shown_at).join(db.Seen, db.Seen.item_id == db.Item.id)
                      .where(db.Seen.user_id == user_id)).all()
        used = s.exec(select(db.Item.url).join(db.Feedback, db.Feedback.item_id == db.Item.id)
                      .where(db.Feedback.user_id == user_id, db.Feedback.action == "써봤음")).all()
        questions_today = s.exec(select(func.count()).select_from(db.Question)
                                 .where(db.Question.user_id == user_id, db.Question.session_date == today)).one()
    return {
        "user_id": user_id, "found": True, "is_test": user.is_test,
        "profile": {"role": user.role, "tools_tags": user.profile_tools_tags, "free_text": user.profile_free_text},
        "weights": weights,
        "used_urls": sorted(set(used)),
        "seen_urls": sorted({url for url, _ in seen}),
        "seen_today_urls": sorted({url for url, shown in seen if shown and _naive(shown) >= start}),
        "questions_today": questions_today,
    }


def test_user_ids() -> list[int]:
    """개발 모드에서 쓰는 is_test 사용자 id."""
    with db.session() as s:
        return list(s.exec(select(db.User.id).where(db.User.is_test == True).order_by(db.User.id)))  # noqa: E712


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
