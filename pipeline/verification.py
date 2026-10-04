"""검증 요청 큐·검증 결과 저장·카드 칸 (계획안 부록 D, 세션 8. 2026-09-15 사용자 결정: 요청은 새 표 verify_requests).

- save_requests: W1 07:00 큐레이터가 고른 검증 요청(하루 최대 5)을 저장. 이미 있는 항목은 건드리지 않는다
- due_requests: 06:00 W1-a가 처리할 것. 전날까지 요청된 대기 + 미완료(3번까지 재시도)
- mark: 상태 기록. 대기 → 완료 | 실패(설치 실패·원문 접근 불가, 되돌림 1 대상) | 미완료(E2B 장애·시간 초과) | 거부(가드·하루 30건)
- save_review: skill_reviews 저장
- 카드 칸: probes → verification(칩 4개), skill_reviews → risk_signal. 고정 문구는 카드 템플릿(web/cards.js, briefing_mail)에 둔다
"""
import re
from datetime import date

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert

import db

MAX_ATTEMPTS = 3
DUE_LIMIT = 10  # 전날 요청 5 + 재시도
OK, FAIL, NA = "성공", "실패", "해당없음"
RISK_LABELS = {"ok": "정상", "caution": "주의", "unverified": "확인 필요", "skipped": "공식 출처, 위험 신호 생략"}
# 확인 필요는 판독 모델과 규칙 검사(정규식)가 엇갈린 경우다. 검증관이 남긴 내부 표시를 읽을 수 있는 말로 (9/24·25 메일 점검)
QUOTE_SOURCES = {"모델: ": "판독 모델만 위험으로 봄", "정규식: ": "규칙 검사만 위험으로 봄"}
QUOTE_MAX = 160


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
            added += len(conn.execute(statement.returning(db.VerifyRequest.item_id)).all())  # rowcount는 -1이 나온다 (9/16 실측)
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
    # 키가 없어 못 띄운 것은 도구 고장이 아니다. "실패" 대신 미확인(키 필요)으로 (10/3 Memanto MOORCHEH_API_KEY)
    keyed = lambda value: ("warn", "미확인(키 필요)") if value == FAIL and auth == "필요" else (chip.get(value, "na"), value)  # noqa: E731
    (run_chip, run_word), (list_chip, list_word) = keyed(row.run), keyed(row.tools_list)
    return {
        "install": {"status": chip.get(row.install, "na"), "label": "설치 해당없음" if remote else f"설치 {row.install}{seconds('install')}"},
        "run": {"status": run_chip, "label": "실행 해당없음" if remote else f"실행 {run_word}"},
        "tools_list": {"status": list_chip,
                       "label": f"도구 {len(row.tools or [])}개" if row.tools_list == OK
                       else f"엔드포인트 {endpoint}" if remote and endpoint else f"도구 목록 {list_word}"},
        "auth_required": {"status": "warn" if auth == "필요" else "ok" if auth == "불필요" else "na",
                          "label": f"{', '.join(row.requirements)} 필요" if auth == "필요" and row.requirements
                          else "인증 필요" if auth == "필요" else "인증 불필요" if auth == "불필요" else "인증 미확인"},
        "probed_at": f"{row.probed_at:%m-%d %H:%M} 샌드박스",
    }


def readable_quote(quote: str | None) -> tuple[str | None, str | None]:
    """반환: (근거, 인용문). 인용문은 마크다운 강조·코드 표시와 줄바꿈을 걷어 한 줄로, 길면 자른다."""
    if not quote:
        return None, None
    raw = next((old for old in QUOTE_SOURCES if quote.startswith(old)), "")
    basis, body = QUOTE_SOURCES.get(raw), quote[len(raw):]
    body = re.sub(r"\s+", " ", re.sub(r"\*\*|__|`", "", body)).strip()
    if len(body) > QUOTE_MAX:
        body = body[:QUOTE_MAX - 1].rstrip() + "…"
    return basis, body


def card_risk(row) -> dict | None:
    """skill_reviews 행 → 카드 risk_signal 칸."""
    if row is None or row.status != "done":
        return None
    level = row.risk_signal or "unverified"
    basis, quote = readable_quote(row.risk_quote)
    return {"level": level, "label": RISK_LABELS.get(level, level), "basis": basis, "quote": quote, "purpose": row.purpose,
            "trigger": row.trigger, "steps": row.steps_summary, "tools_needed": row.tools_needed, "completeness": row.completeness,
            "hits": sorted({h.get("category", "") for h in (row.regex_hits or [])}), "reviewed_at": f"{row.reviewed_at:%m-%d %H:%M}"}


def request_note(kind: str | None, status: str | None, error: str | None, attempts: int) -> str | None:
    """결과가 아직 없는 카드의 메모. 요청 상태를 그대로 옮겨 "검증 예정"이 사실과 어긋나지 않게 한다 (2026-09-26 발송분 점검)."""
    word = "판독" if kind == "skill" else "검증"
    if status == "pending":
        return f"다음 날 06:00 {word} 예정"
    if status == "incomplete":
        again = ", 다음 날 다시" if attempts < MAX_ATTEMPTS else ""
        return f"{word} 미완료({error or '이유 없음'}){again}"[:200]
    return error


def results_for(urls: list[str]) -> dict[str, dict]:
    """카드 링크별 검증 결과. {url: {verification, risk_signal, request_status, note, probe_command}}. 요청만 있고 결과가 없으면 note만."""
    if not urls:
        return {}
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Item.url, db.Item.id, db.VerifyRequest.kind, db.VerifyRequest.status, db.VerifyRequest.last_error,
                                   db.VerifyRequest.attempts)
                            .outerjoin(db.VerifyRequest, db.VerifyRequest.item_id == db.Item.id).where(db.Item.url.in_(urls))).all()
        ids = [r.id for r in rows]
        probes = {p.item_id: p for p in conn.execute(select(db.Probe).where(db.Probe.item_id.in_(ids))).all()} if ids else {}
        reviews = {s.item_id: s for s in conn.execute(select(db.SkillReview).where(db.SkillReview.item_id.in_(ids))).all()} if ids else {}
    out = {}
    for row in rows:
        verification, risk = card_verification(probes.get(row.id)), card_risk(reviews.get(row.id))
        has_result = (verification or risk) and row.status not in ("failed", "rejected")  # 실패 이유는 되돌림 1이 읽는다
        note = None if has_result else request_note(row.kind, row.status, row.last_error, row.attempts or 0)
        if verification or risk or note or row.status:
            out[row.url] = {"verification": verification, "risk_signal": risk, "request_status": row.status, "note": note,
                            "probe_command": getattr(probes.get(row.id), "command", None)}
    return out
