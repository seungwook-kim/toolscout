"""08:00 발송 준비와 발송 기록 (계획안 9.2 W1 "08:00 발송(멱등)", 예외 처리 표 "sent_at 없는 사용자만").

- outbox(day): 그날 sent_at이 비어 있는 briefings를 사용자별 메일 한 통으로 만든다 (카드 전체 또는 empty_reason)
- mark_sent(user_ids, day): 보낸 사용자의 그날 행에 sent_at을 채운다. 이미 채워진 행은 건드리지 않는다
- 실제 발송은 n8n W1의 메일 노드가 한다. 개발 모드(DEV_MODE≠0)는 실제 메일을 보내지 않고 콘솔·DB만 (작업 규칙)
- 개발 모드는 is_test 사용자만 outbox에 넣는다 (작업 규칙 7)
실행(개발 모드 콘솔 발송): uv run python -m pipeline.deliver [--date 2026-09-15] [--preview-dir 폴더]
"""
import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select, update

import db
import models
from agent import tracing
from pipeline import briefing_mail
from pipeline.run_daily import today_kst

log = logging.getLogger("toolscout.deliver")


def outbox(day: date) -> list[dict]:
    """반환: [{user_id, to, role, subject, html, text, cards, empty_reason, trace_ids}] (user_id 순)."""
    query = (select(db.Briefing.user_id, db.Briefing.rank, db.Briefing.card_json, db.Briefing.empty_reason, db.Briefing.trace_id,
                    db.User.email, db.User.role, db.User.is_test)
             .join(db.User, db.User.id == db.Briefing.user_id)
             .where(db.Briefing.date == day, db.Briefing.sent_at.is_(None))
             .order_by(db.Briefing.user_id, db.Briefing.rank))
    if models.dev_mode():
        query = query.where(db.User.is_test == True)  # noqa: E712
    grouped: dict[int, dict] = defaultdict(lambda: {"cards": [], "empty_reason": None, "trace_ids": set()})
    with db.get_engine().connect() as connection:
        for user_id, _rank, card, empty_reason, trace_id, email, role, _is_test in connection.execute(query):
            entry = grouped[user_id]
            entry.update(user_id=user_id, to=email, role=role)
            if card:
                entry["cards"].append(card)
            if empty_reason:
                entry["empty_reason"] = empty_reason
            entry["trace_ids"].add(trace_id)
    messages = []
    for user_id in sorted(grouped):
        entry = grouped[user_id]
        if not entry["to"]:
            log.warning("사용자 %s 이메일 없음, 발송 대상에서 뺌", user_id)
            continue
        mail = briefing_mail.render(day, entry["role"], entry["cards"], entry["empty_reason"])
        messages.append({"user_id": user_id, "to": entry["to"], "role": entry["role"], **mail,
                         "cards": len(entry["cards"]), "empty_reason": entry["empty_reason"],
                         "trace_ids": sorted(entry["trace_ids"])})
    return messages


def mark_sent(user_ids: list[int], day: date) -> int:
    """반환: sent_at을 채운 행 수. 이미 발송 기록이 있는 행은 그대로 둔다 (멱등)."""
    if not user_ids:
        return 0
    with db.get_engine().begin() as connection:
        result = connection.execute(update(db.Briefing).where(
            db.Briefing.date == day, db.Briefing.user_id.in_(user_ids), db.Briefing.sent_at.is_(None))
            .values(sent_at=datetime.now(timezone.utc)))
    return result.rowcount


def console_send(day: date, preview_dir: Path | None = None) -> dict:
    """개발 모드 발송: 실제 메일 대신 콘솔에 제목·받는 사람·카드 수를 찍고 sent_at을 기록한다."""
    if not models.dev_mode():
        raise RuntimeError("운영 발송은 n8n W1 메일 노드가 한다. 이 명령은 개발 모드 전용이다")
    with tracing.span("W1:deliver", kind="chain", input={"date": str(day), "dev_mode": True}) as span:
        messages = outbox(day)
        for message in messages:
            print(f"[개발 모드 발송 안 함] {message['to']} · {message['subject']} · 카드 {message['cards']}장")
            if preview_dir:
                preview_dir.mkdir(parents=True, exist_ok=True)
                (preview_dir / f"{day}_user{message['user_id']}.html").write_text(message["html"], encoding="utf-8")
                (preview_dir / f"{day}_user{message['user_id']}.txt").write_text(message["text"], encoding="utf-8")
        marked = mark_sent([m["user_id"] for m in messages], day)
        result = {"date": str(day), "dev_mode": True, "messages": len(messages), "rows_marked": marked,
                  "users": [{"user_id": m["user_id"], "subject": m["subject"], "cards": m["cards"]} for m in messages]}
        span.update(output=result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="개발 모드 발송 (콘솔·DB만)")
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--preview-dir", type=Path, default=None, help="HTML·텍스트 본문을 저장할 폴더")
    args = parser.parse_args()
    try:
        result = console_send(args.date or today_kst(), args.preview_dir)
    finally:
        tracing.flush()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
