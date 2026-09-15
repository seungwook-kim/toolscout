"""저장 (계획안 9.5, 부록 B 6). 검증 노드를 통과한 카드만 items·briefings·seen에 남긴다.

- items: url 기준 upsert. 제목·링크·요약·주제·메타데이터만 넣고 기사 본문은 넣지 않는다 (작업 규칙 9)
- briefings: 사용자·날짜·항목마다 card_json과 trace_id. sent_at은 발송 단계가 채우므로 여기서는 null
- 재실행 멱등: 오늘 발송한(sent_at 있는) 사용자는 건드리지 않는다. 미발송이면 오늘 브리핑과 그 seen을 지우고 다시 쓴다
- 레지스트리 MCP 여러 개가 같은 저장소 링크를 쓰면 items 한 줄로 합쳐진다. 한 사용자 카드에서 겹치면 앞 순위만 남긴다
- 카드가 0건이면 item_id 없이 empty_reason과 그날 trace_id만 있는 행 하나를 남긴다 (발송 단계가 "오늘 비움"을 알린다)
- 도구 목록: 큐레이터 선별을 통과한 MCP·스킬은 카드가 아니어도 items에 주제·원문 설명과 함께 쌓는다 (관련 카드 F3-b 후보, 2026-09-15 사용자 결정)
- 관련 카드 후보(related_pool): 도구 목록에서 안 본 것을 프로필 도구 태그·써봤음 도구 이름 일치 > 주제 가중치 > 별 수로 100건 이내 (계획안 5장)
"""
import re
from datetime import date

from sqlalchemy import case, delete, func, literal, or_, select
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


def wake_db() -> None:
    """Supabase 깨우기 (계획안 W4, 무료 프로젝트는 오래 안 쓰면 멈춘다). 06:55 예열 때 한 번 접속한다."""
    with db.get_engine().connect() as connection:
        connection.execute(select(1))


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


CATALOG_TYPES = ("mcp", "skill")
DESCRIPTION_CHARS = 300


def save_catalog(today: date, selected: list[dict]) -> int:
    """선별 통과 도구를 items에 upsert한다. 반환: 저장한 도구 수.

    처음 보면 오늘 날짜로 넣고, 이미 있으면(별 수 캐시·지난 카드) 주제·설명·버전·별 수만 새 값으로 채운다. 카드 요약(summary_ko)은 건드리지 않는다.
    """
    unique = {item["url"]: item for item in selected if item.get("type") in CATALOG_TYPES and item.get("url")}
    if not unique:
        return 0
    values = [{"date": today, "type": item["type"], "topic": item.get("topic"), "title": item["title"][:300], "url": url,
               "description": (item.get("summary") or "").strip()[:DESCRIPTION_CHARS] or None, "source": item.get("source", "unknown"),
               "source_tier": SOURCE_TIER.get(item.get("source", "")), "version": item.get("version"), "stars": item.get("stars")}
              for url, item in unique.items()]
    statement = insert(db.Item).values(values)
    statement = statement.on_conflict_do_update(index_elements=["url"], set_={
        "topic": func.coalesce(statement.excluded.topic, db.Item.topic),
        "description": func.coalesce(statement.excluded.description, db.Item.description),
        "version": func.coalesce(statement.excluded.version, db.Item.version),
        "stars": func.coalesce(statement.excluded.stars, db.Item.stars)})
    with db.get_engine().begin() as connection:
        connection.execute(statement)
    return len(values)


RELATED_POOL, RELATED_SCAN = 100, 400
# 거의 모든 도구 이름에 들어가 구별이 안 되는 말. 태그 "mcp"는 모든 MCP와 겹친다
GENERIC_TERMS = {"mcp", "server", "servers", "skill", "skills", "ai", "llm", "agent", "agents", "api", "sdk", "tool", "tools", "app",
                 "com", "io", "github", "official", "the", "and", "for", "plugin", "cli"}


def _terms(text: str) -> list[str]:
    words = re.findall(r"[0-9A-Za-z가-힣+#]+", text.lower())
    return [w for w in words if not w.isdigit() and w not in GENERIC_TERMS and (len(w) >= 3 or re.search(r"[가-힣]{2}", w))]


def related_pool(memory: dict, limit: int = RELATED_POOL) -> list[dict]:
    """관련 카드(F3-b) 후보. 날짜 무관, 주제가 판정된 MCP·스킬 중 안 본 것.

    일치할 말: 프로필 도구 태그(여러 단어면 통째로도) + 써봤음 도구 이름의 단어. 제목·설명에 들어간 말 수 > 주제 가중치 > 별 수 순.
    가중치 -5 주제는 뺀다. 반환 항목에 match(겹친 말 목록)를 붙인다.
    """
    weights, seen = memory.get("weights", {}), set(memory.get("seen_urls", []))
    tags = [t.strip().lower() for t in (memory.get("profile", {}).get("tools_tags") or []) if t and t.strip()]
    terms = [t for t in tags if t not in GENERIC_TERMS] + [w for t in tags for w in _terms(t)]
    with db.get_engine().connect() as connection:
        used = [row[0] for row in connection.execute(select(db.Item.title).where(db.Item.url.in_(memory.get("used_urls") or [])))]
        terms = list(dict.fromkeys(terms + [w for title in used for w in _terms(title)]))[:20]
        columns = (db.Item.title, db.Item.url, db.Item.type, db.Item.source, db.Item.topic, db.Item.description, db.Item.stars,
                   db.Item.version)
        query = select(*columns).where(db.Item.type.in_(CATALOG_TYPES), db.Item.topic.is_not(None))
        if terms:
            points = sum((case((or_(db.Item.title.ilike(f"%{t}%"), db.Item.description.ilike(f"%{t}%")), 1), else_=0) for t in terms),
                         literal(0))
            query = query.order_by(points.desc(), db.Item.stars.desc().nulls_last())
        else:
            query = query.order_by(db.Item.stars.desc().nulls_last())
        rows = connection.execute(query.limit(RELATED_SCAN)).all()
    pool = []
    for row in rows:
        if row.url in seen or weights.get(row.topic, 0) <= -5:
            continue
        text = f"{row.title} {row.description or ''}".lower()
        pool.append({"title": row.title, "url": row.url, "type": row.type, "source": row.source, "topic": row.topic,
                     "description": row.description, "stars": row.stars, "version": row.version,
                     "match": [t for t in terms if t in text]})
    pool.sort(key=lambda i: (-len(i["match"]), -weights.get(i["topic"], 0), -(i["stars"] or 0)))
    return pool[:limit]


def _item_row(item: dict, card: dict, today: date) -> dict:
    return {"date": today, "type": card["type"], "topic": item.get("topic"), "title": card["title"], "url": card["url"],
            "summary_ko": card["summary_ko"], "description": (item.get("summary") or "").strip()[:DESCRIPTION_CHARS] or None,
            "source": item.get("source", "unknown"),
            "source_tier": SOURCE_TIER.get(item.get("source", "")), "version": item.get("version"), "stars": item.get("stars")}


def save_user(user_id: int, today: date, cards: list[dict], items_by_url: dict[str, dict], *,
              trace_id: str | None = None, empty_reason: str | None = None, pool_size: int | None = None) -> dict:
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
                                                          empty_reason=empty_reason, trace_id=trace_id, sent_at=None,
                                                          pool_size=pool_size))
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
                pool_size=pool_size,
                trace_id=card["trace_id"], sent_at=None))
            connection.execute(insert(db.Seen).values(user_id=user_id, item_id=item_id, shown_at=db.utcnow())
                               .on_conflict_do_nothing(index_elements=["user_id", "item_id"]))
    return {"status": "saved", "saved": saved, "duplicates": duplicates}
