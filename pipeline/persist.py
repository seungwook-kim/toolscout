"""저장 (계획안 9.5, 부록 B 6). 검증 노드를 통과한 카드만 items·briefings·seen에 남긴다.

- items: url 기준 upsert. 제목·링크·요약·주제·메타데이터만 넣고 기사 본문은 넣지 않는다 (작업 규칙 9)
- briefings: 사용자·날짜·항목마다 card_json과 trace_id. sent_at은 발송 단계가 채우므로 여기서는 null
- 재실행 멱등: 오늘 발송한(sent_at 있는) 사용자는 건드리지 않는다. 미발송이면 오늘 브리핑과 그 seen을 지우고 다시 쓴다
- 레지스트리 MCP 여러 개가 같은 저장소 링크를 쓰면 items 한 줄로 합쳐진다. 한 사용자 카드에서 겹치면 앞 순위만 남긴다
- 카드가 0건이면 item_id 없이 empty_reason과 그날 trace_id만 있는 행 하나를 남긴다 (발송 단계가 "오늘 비움"을 알린다)
"""
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

import db
from agent import schemas
from pipeline.dedupe import SOURCE_TIER


def sent_user_ids(today: date) -> set[int]:
    """오늘 이미 발송한 사용자."""
    with db.get_engine().connect() as connection:
        rows = connection.execute(select(db.Briefing.user_id).where(
            db.Briefing.date == today, db.Briefing.sent_at.is_not(None)).distinct())
        return {row[0] for row in rows}


def users_with_briefings(today: date) -> set[int]:
    """그날 briefings 행(카드 또는 빈 행)이 있는 사용자. 예약 작업이 놓친 하루 실행을 따라잡을지 볼 때 쓴다."""
    with db.get_engine().connect() as connection:
        rows = connection.execute(select(db.Briefing.user_id).where(db.Briefing.date == today).distinct())
        return {row[0] for row in rows}


def pending_urls(user_id: int, today: date) -> set[str]:
    """오늘 저장했지만 아직 발송하지 않은 카드의 링크. 재실행 때 큐레이터가 '본 항목'으로 빼지 않게 한다."""
    with db.get_engine().connect() as connection:
        rows = connection.execute(select(db.Item.url).join(db.Briefing, db.Briefing.item_id == db.Item.id).where(
            db.Briefing.user_id == user_id, db.Briefing.date == today, db.Briefing.sent_at.is_(None)))
        return {row[0] for row in rows}


def _item_row(item: dict, card: dict, today: date) -> dict:
    return {"date": today, "type": card["type"], "topic": item.get("topic"), "title": card["title"], "url": card["url"],
            "summary_ko": card["summary_ko"], "source": item.get("source", "unknown"),
            "source_tier": SOURCE_TIER.get(item.get("source", "")), "version": item.get("version"), "stars": item.get("stars")}


def save_user(user_id: int, today: date, cards: list[dict], items_by_url: dict[str, dict], *,
              trace_id: str | None = None, empty_reason: str | None = None) -> dict:
    """한 사용자의 오늘 카드를 한 트랜잭션으로 저장한다. 반환: {status, saved, duplicates}.

    cards가 비었으면 empty_reason·trace_id로 빈 행 하나를 남긴다 (status "empty").
    """
    for card in cards:
        schemas.Card.model_validate(card)  # trace_id 없는 카드는 여기서 막힌다 (작업 규칙 10)
    if not cards and not (empty_reason and trace_id):
        raise ValueError("카드가 0건이면 empty_reason과 trace_id가 필요하다")
    with db.get_engine().begin() as connection:
        already_sent = connection.execute(select(func.count()).select_from(db.Briefing).where(
            db.Briefing.user_id == user_id, db.Briefing.date == today, db.Briefing.sent_at.is_not(None))).scalar_one()
        if already_sent:
            return {"status": "skipped_sent", "saved": 0, "duplicates": []}
        old_items = [row[0] for row in connection.execute(select(db.Briefing.item_id).where(
            db.Briefing.user_id == user_id, db.Briefing.date == today, db.Briefing.item_id.is_not(None)))]
        if old_items:
            connection.execute(delete(db.Seen).where(db.Seen.user_id == user_id, db.Seen.item_id.in_(old_items)))
        connection.execute(delete(db.Briefing).where(db.Briefing.user_id == user_id, db.Briefing.date == today))
        if not cards:
            connection.execute(insert(db.Briefing).values(user_id=user_id, date=today, item_id=None, rank=0, card_json=None,
                                                          empty_reason=empty_reason, trace_id=trace_id, sent_at=None))
            return {"status": "empty", "saved": 0, "duplicates": []}

        saved, duplicates, used = 0, [], set()
        for card in cards:
            row = _item_row(items_by_url.get(card["url"], {}), card, today)
            statement = insert(db.Item).values(row)
            statement = statement.on_conflict_do_update(index_elements=["url"], set_={
                "topic": func.coalesce(statement.excluded.topic, db.Item.topic),
                "summary_ko": func.coalesce(db.Item.summary_ko, statement.excluded.summary_ko)}).returning(db.Item.id)
            item_id = connection.execute(statement).scalar_one()
            if item_id in used:
                duplicates.append({"title": card["title"], "url": card["url"]})
                continue
            used.add(item_id)
            saved += 1
            connection.execute(insert(db.Briefing).values(
                user_id=user_id, date=today, item_id=item_id, rank=saved, card_json=card | {"item_id": item_id, "rank": saved},
                trace_id=card["trace_id"], sent_at=None))
            connection.execute(insert(db.Seen).values(user_id=user_id, item_id=item_id, shown_at=db.utcnow())
                               .on_conflict_do_nothing(index_elements=["user_id", "item_id"]))
    return {"status": "saved", "saved": saved, "duplicates": duplicates}
