"""두 층 기억 읽기·쓰기·잊기 (계획안 5장 기억 설계, 부록 C). 합치기(주간 정규화)는 W4에서 붙인다.

- 전체 기억: 구조화 프로필(직군 선택·주제 10개 관심도·쓰는 도구 태그·자유 한 줄), 주제 가중치, 써봤음 항목
- 일일 기억: 오늘 보여준 항목, 오늘 질문 횟수
- 쓰기: 프로필 저장(가중치 초기값), 피드백 버튼 (routes/feedback.py가 apply_feedback을 부른다)
- 잊기: 「내 기억 지우기」는 weights·seen·feedback 삭제, 계정 삭제는 사용자와 딸린 기록 전부
검색도 임베딩도 없다. 기사 본문·다른 사용자 정보·검증 로그는 넣지 않는다.
"""
from datetime import date, datetime, time, timezone

from sqlalchemy import delete
from sqlmodel import func, select

import db
from agent.schemas import TOPICS

WEIGHT_MIN, WEIGHT_MAX = -5, 5
ROLE_CHOICES = ["개발자", "기획자", "마케터", "학생", "기타"]
NOTIFY_TIMES = ["08:00", "09:00", "12:00", "18:00"]
CHANNELS = ["email"]  # 카카오는 나중
# 직군 프리셋: 주제 10개 초기 관심도. 설정 화면에서 접힌 상태로 채워지고 사용자가 고칠 수 있다 (계획안 작업 규칙 "직군 프리셋 기본값")
ROLE_PRESETS: dict[str, dict[str, int]] = {
    "개발자": {"model_release": 2, "agent_framework": 3, "mcp_tools": 3, "coding_tools": 3, "pricing": 1,
             "open_local": 2, "data_rag": 2, "safety_policy": 1, "automation": 1, "industry": 0},
    "기획자": {"model_release": 2, "agent_framework": 1, "mcp_tools": 0, "coding_tools": 0, "pricing": 2,
             "open_local": 0, "data_rag": 1, "safety_policy": 1, "automation": 2, "industry": 3},
    "마케터": {"model_release": 1, "agent_framework": 0, "mcp_tools": 0, "coding_tools": -1, "pricing": 1,
             "open_local": -1, "data_rag": 0, "safety_policy": 0, "automation": 3, "industry": 2},
    "학생": {"model_release": 3, "agent_framework": 2, "mcp_tools": 1, "coding_tools": 2, "pricing": 1,
           "open_local": 2, "data_rag": 2, "safety_policy": 0, "automation": 0, "industry": 0},
    "기타": {topic: 0 for topic in TOPICS},
}


class ProfileError(ValueError):
    pass


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


def profile(user_id: int) -> dict:
    """설정 화면용. 가중치가 없으면 직군 프리셋(직군도 없으면 0)으로 채워 보여 준다."""
    with db.session() as s:
        user = s.get(db.User, user_id)
        weights = {w.topic: w.weight for w in s.exec(select(db.Weight).where(db.Weight.user_id == user_id))}
    base = ROLE_PRESETS.get(user.role, ROLE_PRESETS["기타"])
    return {"role": user.role, "tools_tags": user.profile_tools_tags or [], "free_text": user.profile_free_text or "",
            "weights": {topic: weights.get(topic, base.get(topic, 0)) for topic in TOPICS},
            "notify_time": user.notify_time, "channel": user.channel, "has_weights": bool(weights)}


def save_profile(user_id: int, *, role: str, tools_tags: list[str], free_text: str | None, weights: dict[str, int],
                 notify_time: str = "08:00", channel: str = "email") -> None:
    if role not in ROLE_CHOICES:
        raise ProfileError("직군을 골라 주세요")
    if notify_time not in NOTIFY_TIMES or channel not in CHANNELS:
        raise ProfileError("알림 채널·시간 값이 올바르지 않아요")
    tags = list(dict.fromkeys(t.strip()[:30] for t in tools_tags if t and t.strip()))[:15]
    text = (free_text or "").strip()[:100] or None
    clean = {topic: max(WEIGHT_MIN, min(WEIGHT_MAX, int(weights.get(topic, 0)))) for topic in TOPICS}
    with db.session() as s:
        user = s.get(db.User, user_id)
        user.role, user.profile_tools_tags, user.profile_free_text = role, tags, text
        user.notify_time, user.channel = notify_time, channel
        s.add(user)
        existing = {w.topic: w for w in s.exec(select(db.Weight).where(db.Weight.user_id == user_id))}
        for topic, value in clean.items():
            row = existing.get(topic) or db.Weight(user_id=user_id, topic=topic)
            row.weight, row.updated_at = value, db.utcnow()
            s.add(row)
        s.commit()


def forget(user_id: int) -> dict:
    """「내 기억 지우기」: weights·seen·feedback 삭제 (부록 C). 다음 날은 프로필만으로."""
    with db.get_engine().begin() as conn:
        counts = {table.__tablename__: conn.execute(delete(table).where(table.user_id == user_id)).rowcount
                  for table in (db.Weight, db.Seen, db.Feedback)}
    return counts


def delete_account(user_id: int) -> None:
    """계정 삭제: 사용자와 딸린 기록 전부."""
    with db.get_engine().begin() as conn:
        for table in (db.Weight, db.Seen, db.Feedback, db.Question, db.Briefing):
            conn.execute(delete(table).where(table.user_id == user_id))
        conn.execute(delete(db.User).where(db.User.id == user_id))


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
