"""검증 요청 큐·검증 결과 저장·카드 칸 (계획안 부록 D, 세션 8. 2026-09-15 사용자 결정: 요청은 새 표 verify_requests).

- save_requests: W1 07:00 큐레이터가 고른 검증 요청(하루 최대 5)을 저장. 이미 있는 항목은 건드리지 않는다
- due_requests: 06:00 W1-a가 처리할 것. 전날까지 요청된 대기 + 미완료(3번까지 재시도)
- mark: 상태 기록. 대기 → 완료 | 실패(설치 실패·원문 접근 불가, 되돌림 1 대상) | 미완료(E2B 장애·시간 초과) | 거부(가드·하루 30건)
- save_review: skill_reviews 저장
- 카드 칸: probes → verification(칩 4개), skill_reviews → risk_signal. 고정 문구는 카드 템플릿(web/cards.js, briefing_mail)에 둔다
"""
from datetime import date

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert

import db

MAX_ATTEMPTS = 3
DUE_LIMIT = 10  # 전날 요청 5 + 재시도
OK, FAIL, NA = "성공", "실패", "해당없음"
RISK_LABELS = {"ok": "정상", "caution": "주의", "unverified": "확인 필요", "skipped": "공식 출처, 위험 신호 생략"}


def install_info(item: dict) -> dict | None:
    """수집 항목의 설치 정보(레지스트리 packages·remotes, 스킬 SKILL.md 주소)를 요청에 담을 모양으로."""
    info = {k: item[k] for k in ("install", "skill_url") if item.get(k)}
    return info or None


def save_requests(day: date, requests: list[dict]) -> int:
    """반환: 새로 넣은 요청 수. items에 없는 링크는 건너뛴다 (도구 목록 쌓기가 먼저 넣는다)."""
    if not requests:
        return 0
    with db.get_engine().begin() as conn:
        ids = dict(conn.execute(select(db.Item.url, db.Item.id).where(db.Item.url.in_([r["url"] for r in requests]))).all())
        added = 0
        for request in requests:
            item_id = ids.get(request["url"])
            if item_id is None:
                continue
            kind = "skill" if request.get("type") == "skill" else "mcp"
            statement = insert(db.VerifyRequest).values(
                item_id=item_id, kind=kind, depth=request.get("depth") or ("read" if kind == "skill" else "full"),
                reason=(request.get("verify_reason") or "")[:200], install=install_info(request), requested_on=day,
                status="pending", attempts=0, updated_at=db.utcnow()).on_conflict_do_nothing(index_elements=["item_id"])
            added += conn.execute(statement).rowcount
    return added


def item_id_for(url: str) -> int | None:
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.Item.id).where(db.Item.url == url)).scalar()


def due_requests(day: date, limit: int = DUE_LIMIT) -> list[dict]:
    with db.get_engine().connect() as conn:
        rows = conn.execute(
            select(db.VerifyRequest.item_id, db.VerifyRequest.kind, db.VerifyRequest.depth, db.VerifyRequest.reason,
                   db.VerifyRequest.install, db.VerifyRequest.attempts, db.Item.title, db.Item.url, db.Item.type, db.Item.description,
                   db.Item.topic)
            .join(db.Item, db.Item.id == db.VerifyRequest.item_id)
            .where(or_((db.VerifyRequest.status == "pending") & (db.VerifyRequest.requested_on < day),
                       (db.VerifyRequest.status == "incomplete") & (db.VerifyRequest.attempts < MAX_ATTEMPTS)))
            .order_by(db.VerifyRequest.requested_on, db.VerifyRequest.item_id).limit(limit)).all()
    return [{"item_id": r.item_id, "kind": r.kind, "depth": r.depth, "reason": r.reason, "install": r.install or {},
             "attempts": r.attempts, "title": r.title, "url": r.url, "type": r.type, "description": r.description, "topic": r.topic}
            for r in rows]


def mark(item_id: int, status: str, error: str | None = None) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(update(db.VerifyRequest).where(db.VerifyRequest.item_id == item_id).values(
            status=status, attempts=db.VerifyRequest.attempts + 1, last_error=(error or "")[:300] or None, updated_at=db.utcnow()))


def save_review(item_id: int, review: dict) -> None:
    values = {"item_id": item_id, **{k: review.get(k) for k in ("purpose", "trigger", "steps_summary", "tools_needed", "completeness",
                                                                "risk_signal", "risk_quote", "official", "source_url", "llm_signal",
                                                                "status")},
              "regex_hits": review.get("regex_hits") or [], "reviewed_at": db.utcnow().replace(tzinfo=None)}
    statement = insert(db.SkillReview).values(values)
    statement = statement.on_conflict_do_update(index_elements=["item_id"], set_={k: statement.excluded[k] for k in values if k != "item_id"})
    with db.get_engine().begin() as conn:
        conn.execute(statement)


def card_verification(row) -> dict | None:
    """probes 행 → 카드 verification 칸 (web/cards.js 칩 규격: status ok|bad|warn|na, label). 완료가 아니면 None."""
    if row is None or row.status != "done":
        return None
    stages = row.stages or {}
    chip = {OK: "ok", FAIL: "bad", NA: "na"}
    remote = row.kind == "remote"
    seconds = lambda stage: f" {ms / 1000:.1f}s" if (ms := (stages.get(stage) or {}).get("ms")) else ""  # noqa: E731
    auth = (stages.get("auth") or {}).get("status")
    endpoint = (stages.get("tools_list") or {}).get("endpoint")
    return {
        "install": {"status": chip.get(row.install, "na"), "label": "설치 해당없음" if remote else f"설치 {row.install}{seconds('install')}"},
        "run": {"status": chip.get(row.run, "na"), "label": "실행 해당없음" if remote else f"실행 {row.run}"},
        "tools_list": {"status": chip.get(row.tools_list, "na"),
                       "label": f"도구 {len(row.tools or [])}개" if row.tools_list == OK
                       else f"엔드포인트 {endpoint}" if remote and endpoint else f"도구 목록 {row.tools_list}"},
        "auth_required": {"status": "warn" if auth == "필요" else "ok" if auth == "불필요" else "na",
                          "label": f"{', '.join(row.requirements)} 필요" if auth == "필요" and row.requirements
                          else "인증 필요" if auth == "필요" else "인증 불필요" if auth == "불필요" else "인증 미확인"},
        "probed_at": f"{row.probed_at:%m-%d %H:%M} 샌드박스",
    }


def card_risk(row) -> dict | None:
    """skill_reviews 행 → 카드 risk_signal 칸."""
    if row is None or row.status != "done":
        return None
    level = row.risk_signal or "unverified"
    return {"level": level, "label": RISK_LABELS.get(level, level), "quote": row.risk_quote, "purpose": row.purpose,
            "trigger": row.trigger, "steps": row.steps_summary, "tools_needed": row.tools_needed, "completeness": row.completeness,
            "hits": sorted({h.get("category", "") for h in (row.regex_hits or [])}), "reviewed_at": f"{row.reviewed_at:%m-%d %H:%M}"}


def results_for(urls: list[str]) -> dict[str, dict]:
    """카드 링크별 검증 결과. {url: {verification, risk_signal, request_status, note}}. 요청만 있고 결과가 없으면 note만."""
    if not urls:
        return {}
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Item.url, db.Item.id, db.VerifyRequest.status, db.VerifyRequest.last_error)
                            .outerjoin(db.VerifyRequest, db.VerifyRequest.item_id == db.Item.id).where(db.Item.url.in_(urls))).all()
        ids = [r.id for r in rows]
        probes = {p.item_id: p for p in conn.execute(select(db.Probe).where(db.Probe.item_id.in_(ids))).all()} if ids else {}
        reviews = {s.item_id: s for s in conn.execute(select(db.SkillReview).where(db.SkillReview.item_id.in_(ids))).all()} if ids else {}
    out = {}
    for row in rows:
        verification, risk = card_verification(probes.get(row.id)), card_risk(reviews.get(row.id))
        note = None
        if row.status in ("failed", "rejected") and row.last_error:
            note = row.last_error
        if verification or risk or note or row.status:
            out[row.url] = {"verification": verification, "risk_signal": risk, "request_status": row.status, "note": note}
    return out
