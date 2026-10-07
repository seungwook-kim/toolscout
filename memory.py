"""두 층 기억 읽기·쓰기·합치기·잊기 (계획안 5장 기억 설계, 부록 C).

- 전체 기억: 구조화 프로필(직군 선택·주제 10개 관심도·쓰는 도구 태그·자유 한 줄), 주제 가중치, 써봤음 항목
- 일일 기억: 오늘 보여준 항목, 오늘 질문 횟수
- 쓰기: 프로필 저장(가중치 초기값), 피드백 버튼 (routes/feedback.py가 apply_feedback을 부른다)
- 합치기: 매주 월요일, 30일 동안 누르지 않은 주제는 피드백으로 바뀐 만큼 되돌려 프로필 기준값(직군 프리셋, 설정에서 고친 값)으로
- 잊기: 「내 기억 지우기」는 weights·seen·feedback 삭제, 계정 삭제는 사용자와 딸린 기록 전부
검색도 임베딩도 없다. 기사 본문·다른 사용자 정보·검증 로그는 넣지 않는다.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import delete, update
from sqlmodel import func, select

import db
from agent.owners import RECENT_DAYS
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
    recent = start - timedelta(days=RECENT_DAYS)
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
        # 도구 게시자 반복 줄이기(agent/owners.py). 오늘 것은 빼서 같은 날 다시 만들 때 자기 카드에 막히지 않게
        "seen_recent_urls": sorted({url for url, shown in seen if shown and recent <= _naive(shown) < start}),
        "questions_today": questions_today,
    }


def test_user_ids() -> list[int]:
    """개발 모드에서 쓰는 is_test 사용자 id. 데모 프로필은 뺀다(2026-10-08부터 /demo가 고정 예시라 하루 실행 대상이 아니다)."""
    with db.session() as s:
        return list(s.exec(select(db.User.id).where(db.User.is_test == True, db.User.is_demo == False).order_by(db.User.id)))  # noqa: E712


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
        changed = [topic for topic, value in clean.items() if topic in existing and existing[topic].weight != value]
        for topic, value in clean.items():
            row = existing.get(topic) or db.Weight(user_id=user_id, topic=topic)
            row.weight, row.updated_at = value, db.utcnow()
            s.add(row)
        if changed:  # 설정에서 값을 고친 주제는 그 값이 새 기준이다. 합치기가 예전 피드백만큼 다시 빼지 않게 기록을 0으로
            item_ids = select(db.Item.id).where(db.Item.topic.in_(changed))
            s.execute(update(db.Feedback).where(db.Feedback.user_id == user_id, db.Feedback.item_id.in_(item_ids))
                   .values(weight_delta=0))
        s.commit()


ACTIONS = ("관심없음", "써봤음", "이상함")
WEIRD_REASONS = ("번역 어색", "사실 틀림", "나랑 상관없음")
ACTION_DELTA = {"관심없음": -1, "써봤음": 1, "이상함": 0}


class FeedbackError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def apply_feedback(user_id: int, item_id: int, action: str) -> dict:
    """피드백 버튼 (부록 C). 같은 버튼을 다시 누르면 취소하고 가중치를 되돌린다.

    관심없음: 그 항목 주제 -1, 써봤음: 그 항목 주제(도구 종류) +1, 이상함: 기록만(사유는 note로). 가중치는 -5~+5에서 멈춘다.
    반환: {status: recorded|cancelled, feedback_id, topic, topic_label, weight, message}
    """
    if action not in ACTIONS:
        raise FeedbackError("버튼 값이 올바르지 않아요")
    with db.session() as s:
        in_my_briefing = s.exec(select(db.Briefing.id).where(db.Briefing.user_id == user_id, db.Briefing.item_id == item_id)).first()
        if in_my_briefing is None:
            raise FeedbackError("내 브리핑에 없는 항목이에요", status=403)
        item = s.get(db.Item, item_id)
        topic = item.topic if item and item.topic in TOPICS else None
        label = TOPICS.get(topic or "", "")
        existing = s.exec(select(db.Feedback).where(db.Feedback.user_id == user_id, db.Feedback.item_id == item_id,
                                                    db.Feedback.action == action).order_by(db.Feedback.id.desc())).first()
        weight_row = s.get(db.Weight, (user_id, topic)) if topic else None
        current = weight_row.weight if weight_row else 0
        if existing is not None:
            new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, current - existing.weight_delta))
            s.delete(existing)
            status, feedback_id = "cancelled", existing.id
            message = f"취소했어요. {label} 가중치를 되돌렸어요" if existing.weight_delta else "취소했어요"
        else:
            new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, current + ACTION_DELTA[action])) if topic else current
            row = db.Feedback(user_id=user_id, item_id=item_id, action=action, weight_delta=new_weight - current)
            s.add(row)
            s.flush()
            status, feedback_id = "recorded", row.id
            message = _feedback_message(action, label, new_weight)
        if topic and new_weight != current:
            weight_row = weight_row or db.Weight(user_id=user_id, topic=topic)
            weight_row.weight, weight_row.updated_at = new_weight, db.utcnow()
            s.add(weight_row)
        if status == "recorded" and s.get(db.Seen, (user_id, item_id)) is None:
            s.add(db.Seen(user_id=user_id, item_id=item_id))
        s.commit()
    return {"status": status, "feedback_id": feedback_id, "topic": topic, "topic_label": label, "weight": new_weight,
            "message": message}


def _feedback_message(action: str, label: str, weight: int) -> str:
    if action == "관심없음":
        if not label:
            return "관심없음으로 기록했어요"
        return f"{label} 주제는 이제 카드로 보여 드리지 않을게요" if weight <= WEIGHT_MIN else f"내일부터 {label} 주제는 뒤로 뺄게요"
    if action == "써봤음":
        return f"써봤음으로 기록했어요. {label} 주제 도구를 더 챙길게요" if label else "써봤음으로 기록했어요"
    return "알려 주셔서 고마워요. 어떤 점이 이상했는지 골라 주세요"


def note_feedback(user_id: int, feedback_id: int, *, reason: str | None = None, memo: str | None = None) -> dict:
    """이상함 사유(3택)나 써봤음 메모를 붙인다. 본인 피드백만."""
    with db.session() as s:
        row = s.get(db.Feedback, feedback_id)
        if row is None or row.user_id != user_id:
            raise FeedbackError("내 피드백이 아니에요", status=403)
        if reason is not None:
            if row.action != "이상함" or reason not in WEIRD_REASONS:
                raise FeedbackError("사유 값이 올바르지 않아요")
            row.reason = reason
        if memo is not None:
            if row.action != "써봤음":
                raise FeedbackError("메모는 써봤음에만 남길 수 있어요")
            row.memo = memo.strip()[:200] or None
        s.add(row)
        s.commit()
    return {"ok": True, "message": "사유를 기록했어요" if reason else "메모를 저장했어요"}


MERGE_QUIET_DAYS = 30


def merge_weights(today: date | None = None, user_ids: list[int] | None = None) -> dict:
    """주간 기억 합치기 (계획안 5장 기억 설계 표, 부록 C 5, W4 월요일). user_ids가 없으면 모든 사용자 (검수는 검수용 사용자만).

    - -5~+5 정규화는 쓰기 때 자르기와 DB 제약(ck_weights_range)으로 이미 지켜진다
    - 주제마다 마지막으로 누른 때(이상함 포함)가 30일보다 오래됐고 피드백이 바꿔 둔 값(weight_delta 합)이 남아 있으면 그만큼 되돌린다.
      설정을 고친 적 없으면 직군 프리셋 값으로 돌아간다 (2026-09-15 사용자 결정). 되돌린 피드백은 기록을 남기고 weight_delta만 0으로
    - 여러 번 돌려도 같다 (두 번째에는 되돌릴 값이 없다)
    반환: {users, topics, reverted: [{user_id, topic, before, after}]}
    """
    today = today or date.today()
    cutoff = datetime.combine(today - timedelta(days=MERGE_QUIET_DAYS), time.min)
    reverted = []
    with db.get_engine().begin() as conn:
        rows = conn.execute(select(db.Feedback.user_id, db.Item.topic, func.max(db.Feedback.created_at), func.sum(db.Feedback.weight_delta))
                            .join(db.Item, db.Item.id == db.Feedback.item_id).where(db.Item.topic.is_not(None))
                            .where(db.Feedback.user_id.in_(user_ids) if user_ids is not None else True)
                            .group_by(db.Feedback.user_id, db.Item.topic)).all()
        for user_id, topic, last_at, pending in rows:
            if not pending or _naive(last_at) >= cutoff:
                continue
            current = conn.execute(select(db.Weight.weight).where(db.Weight.user_id == user_id, db.Weight.topic == topic)).scalar()
            if current is None:
                continue
            after = max(WEIGHT_MIN, min(WEIGHT_MAX, current - pending))
            conn.execute(update(db.Weight).where(db.Weight.user_id == user_id, db.Weight.topic == topic)
                         .values(weight=after, updated_at=db.utcnow()))
            conn.execute(update(db.Feedback).where(db.Feedback.user_id == user_id,
                                                   db.Feedback.item_id.in_(select(db.Item.id).where(db.Item.topic == topic)))
                         .values(weight_delta=0))
            reverted.append({"user_id": user_id, "topic": topic, "before": current, "after": after})
    return {"users": len({r[0] for r in rows}), "topics": len(rows), "reverted": reverted}


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
