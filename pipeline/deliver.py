"""08:00 발송 (계획안 9.2 W1 "08:00 발송(멱등)", 예외 처리 표 "sent_at 없는 사용자만"). n8n 없이 앱이 직접 보낸다 (2026-09-15 사용자 결정).

- outbox(day): 그날 sent_at이 비어 있는 briefings를 사용자별 메일 한 통으로 만든다 (카드 전체 또는 empty_reason).
  공개 데모 프로필(users.is_demo)은 가짜 주소라 메일을 만들지 않는다 (2026-09-16)
- send_day(day): Gmail SMTP(smtp.gmail.com 465)로 보내고, 한 통 보낼 때마다 그 사용자의 sent_at을 채운다. 실패한 사용자는 비워 둔다
- 모든 모드에서 사용자마다 한 통, 운영과 같은 모양이다 (2026-09-28 사용자 결정 "실전으로 갈 거라 메일도 다 수정해").
  개발 모드(DEV_MODE≠0)는 is_test 사용자만이고, 실제 주소로는 ADMIN_EMAILS(개발자 본인) 계정 것만 그 주소로 보낸다.
  가짜 테스트 프로필(.test 주소)은 받는 사람을 ADMIN_EMAILS로 바꾸고 제목 앞에 [테스트 프로필 직군]을 붙인다.
  예전의 개발 모드 묶음 메일([개발 모드] 제목·프로필 목차, 2026-09-16)은 없앴다. ADMIN_EMAILS가 비어 있으면 실제로 보내지 않고 콘솔·DB만
- 운영 모드: users.email로 보낸다. GMAIL_USER·GMAIL_APP_PASSWORD 값은 로그에 쓰지 않는다
실행: uv run python -m pipeline.deliver [--date 2026-09-15] [--console] [--preview-dir 폴더]
"""
import argparse
import json
import logging
import os
import smtplib
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import select, update

import db
import models
from agent import tracing
from pipeline import briefing_mail, weekly
from pipeline.run_daily import today_kst

log = logging.getLogger("toolscout.deliver")

SMTP_HOST, SMTP_PORT, SMTP_TIMEOUT = "smtp.gmail.com", 465, 30


class MailError(Exception):
    pass


class DirMailer:
    """검수용. MAIL_FAKE_DIR 환경변수가 있으면 SMTP 대신 그 폴더에 메일을 JSON 파일로 쓴다 (실제로 보내지 않음)."""

    def __init__(self, host=None, port=None, timeout=None):
        self.folder = Path(os.environ["MAIL_FAKE_DIR"])

    def __enter__(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        return None

    def send_message(self, message: EmailMessage):
        body = {"to": message["To"], "subject": message["Subject"],
                "text": message.get_body(("plain",)).get_content() if message.is_multipart() else message.get_content()}
        name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
        (self.folder / name).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")


def default_smtp_factory():
    return DirMailer if os.environ.get("MAIL_FAKE_DIR") else smtplib.SMTP_SSL


def send_single(recipients: list[str], subject: str, text: str, html: str | None = None, smtp_factory=None) -> None:
    """메일 한 통 (로그인 링크 등). 실패하면 MailError. 설정 값은 오류 문구에 넣지 않는다."""
    sender, password = os.environ.get("GMAIL_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    factory = smtp_factory or default_smtp_factory()
    if factory is not DirMailer and not (sender and password):
        raise MailError("GMAIL_USER 또는 GMAIL_APP_PASSWORD 비어있음")
    email = EmailMessage()
    email["From"] = f"toolscout <{sender or 'toolscout@example.test'}>"
    email["To"] = ", ".join(recipients)
    email["Subject"] = subject
    email.set_content(text)
    if html:
        email.add_alternative(html, subtype="html")
    try:
        with factory(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
            smtp.login(sender, password)
            smtp.send_message(email)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc


def admin_emails() -> list[str]:
    return [e.strip() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]


def send_alert(title: str, lines: list[str], smtp_factory=None) -> str:
    """실패 알림 (계획안 W4). ADMIN_EMAILS에게 한 통. 반환: sent / no_admin / mail_error. 오류 값·설정 값은 넣지 않는다."""
    admins = admin_emails()
    if not admins:
        log.warning("실패 알림 받을 ADMIN_EMAILS 없음: %s", title)
        return "no_admin"
    text = "\n".join(lines + ["", "앱 로그(app.log)와 GET /api/w1/status에서 자세한 내용을 볼 수 있어요."])
    try:
        send_single(admins, f"[toolscout 실패 알림] {title}", text, smtp_factory=smtp_factory)
        return "sent"
    except MailError as exc:
        log.warning("실패 알림 메일도 못 보냄(%s): %s", str(exc).split(":")[0], title)
        return "mail_error"


def outbox(day: date, notify_until: str | None = None) -> list[dict]:
    """반환: [{user_id, to, role, subject, html, text, cards, empty_reason, trace_ids}] (user_id 순)."""
    query = (select(db.Briefing.user_id, db.Briefing.card_json, db.Briefing.empty_reason, db.Briefing.trace_id,
                    db.User.email, db.User.role)
             .join(db.User, db.User.id == db.Briefing.user_id)
             .where(db.Briefing.date == day, db.Briefing.sent_at.is_(None), db.User.is_demo == False)  # noqa: E712
             .where(db.User.notify_time <= notify_until if notify_until else True)
             .order_by(db.Briefing.user_id, db.Briefing.rank))
    if models.dev_mode():
        query = query.where(db.User.is_test == True)  # noqa: E712
    grouped: dict[int, dict] = defaultdict(lambda: {"cards": [], "empty_reason": None, "trace_ids": set()})
    with db.get_engine().connect() as connection:
        for user_id, card, empty_reason, trace_id, email, role in connection.execute(query):
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
        from routes import watermark
        from routes.feedback import feedback_link  # 메일 버튼은 웹앱 /f 서명 링크

        links = lambda card, action, uid=user_id: feedback_link(uid, card["item_id"], action)  # noqa: E731
        mail = briefing_mail.render(day, entry["role"], entry["cards"], entry["empty_reason"], links,
                                    weekly=weekly.block(user_id, day),  # 금요일만 "이번 주 요약"
                                    mark=watermark.mark_for(user_id))  # 받는 사람만 아는 보이지 않는 표식 (2026-10-09)
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


def addressed(message: dict, dev: bool, admins: list[str]) -> tuple[dict, list[str]]:
    """(보낼 메일, 받는 사람). 운영 모드와 개발자 본인 계정은 그대로 본인 주소로. 개발 모드의 가짜 테스트 프로필은
    ADMIN_EMAILS로 돌리고 제목 앞에 [테스트 프로필 직군]을 붙여 본인 브리핑과 구분한다 (작업 규칙: 개발 모드 실제 발송은 관리자에게만)."""
    own = (message.get("to") or "").lower() in {a.lower() for a in admins}
    if not dev or own:
        return message, [message["to"]]
    return message | {"subject": f"[테스트 프로필 {message.get('role') or ''}] {message['subject']}"}, admins


def build_email(mail: dict, sender: str, recipients: list[str]) -> EmailMessage:
    """mail: {subject, text, html} (사용자 한 명분)."""
    email = EmailMessage()
    email["From"] = f"toolscout <{sender}>"
    email["To"] = ", ".join(recipients)
    email["Subject"] = mail["subject"]
    email.set_content(mail["text"])
    email.add_alternative(mail["html"], subtype="html")
    return email


def send_day(day: date, notify_until: str | None = None, *, console: bool = False, preview_dir: Path | None = None,
             smtp_factory=None) -> dict:
    """그날 미발송 메일을 보낸다. 반환: {date, dev_mode, mode, sent[], failed[], rows_marked}.

    mode: smtp(실제 발송) / console(보내지 않고 콘솔·DB만) / config_missing(메일 설정 없음, 기록 안 함)
    """
    dev = models.dev_mode()
    admins = admin_emails()
    smtp_factory = smtp_factory or default_smtp_factory()
    sender, password = os.environ.get("GMAIL_USER", "").strip(), os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if smtp_factory is DirMailer:
        sender, password = sender or "toolscout@example.test", password or "fake"
    with tracing.span("W1:send", kind="chain", input={"date": str(day), "dev_mode": dev}) as span:
        messages = outbox(day, notify_until)
        for message in messages:
            if preview_dir:
                preview_dir.mkdir(parents=True, exist_ok=True)
                (preview_dir / f"{day}_user{message['user_id']}.html").write_text(message["html"], encoding="utf-8")
                (preview_dir / f"{day}_user{message['user_id']}.txt").write_text(message["text"], encoding="utf-8")
        mode = "console" if console or (dev and not admins) else "smtp"
        if mode == "smtp" and not (sender and password):
            mode = "config_missing"
        sent, failed, rows = [], [], 0
        if not messages:
            pass
        elif mode == "console":
            for message in messages:
                print(f"[발송 안 함] {message['to']} · {message['subject']} · 카드 {message['cards']}장")
            sent = [m["user_id"] for m in messages]
            rows = mark_sent(sent, day)
        elif mode == "config_missing":
            failed = [{"user_id": m["user_id"], "error": "GMAIL_USER 또는 GMAIL_APP_PASSWORD 비어있음"} for m in messages]
        else:
            try:
                with smtp_factory(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as smtp:
                    smtp.login(sender, password)
                    for message in messages:  # 사용자마다 각자 한 통 (개발 모드도 운영과 같은 모양, 2026-09-28)
                        mail, recipients = addressed(message, dev, admins)
                        try:
                            smtp.send_message(build_email(mail, sender, recipients))
                            rows += mark_sent([message["user_id"]], day)  # 한 통마다 기록해 중간에 죽어도 다시 보내지 않게
                            sent.append(message["user_id"])
                        except (smtplib.SMTPException, OSError) as exc:
                            failed.append({"user_id": message["user_id"], "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            except (smtplib.SMTPException, OSError) as exc:  # 연결·로그인 실패는 남은 사용자 전부 실패
                done = set(sent) | {f["user_id"] for f in failed}
                failed += [{"user_id": m["user_id"], "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
                           for m in messages if m["user_id"] not in done]
        result = {"date": str(day), "dev_mode": dev, "mode": mode, "messages": len(messages), "sent": sent, "failed": failed,
                  "rows_marked": rows, "recipients": "ADMIN_EMAILS" if dev and mode == "smtp" else "users.email",
                  "mails": len(sent) + len(failed) if mode == "smtp" else 0}
        span.update(output=result, level="WARNING" if failed else "DEFAULT")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="브리핑 메일 발송")
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--console", action="store_true", help="보내지 않고 콘솔·DB만")
    parser.add_argument("--preview-dir", type=Path, default=None, help="HTML·텍스트 본문을 저장할 폴더")
    args = parser.parse_args()
    try:
        result = send_day(args.date or today_kst(), console=args.console, preview_dir=args.preview_dir)
    finally:
        tracing.flush()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
