"""앱 바깥 감시 (2026-09-23 사용자 요청). 앱이 통째로 죽으면 앱이 보내는 실패 알림도 안 나가서, 앱과 따로 도는 확인이 필요하다.

실행: uv run python -m pipeline.watchdog
Windows 작업 `toolscout watchdog`이 매일 08:30·09:30·12:30·18:30에 부른다(놓치면 켜질 때 바로, %LOCALAPPDATA%\\toolscout\\watchdog.ps1).
- 앱이 응답하는지(GET /api/health)
- 알림 시각이 30분 넘게 지난 대상 사용자(데모 제외)에게 오늘 메일이 나갔는지(briefings.sent_at). 안 나갔으면 브리핑이 없는지(실행 문제)·있는데 안 나갔는지(발송 문제)를 나눈다
문제가 있으면 deliver.send_alert로 ADMIN_EMAILS에 한 통. 같은 날 같은 문제는 한 번만(상태 파일 watchdog.json).
22:00 뒤와 06:00 전에는 보지 않는다. 브리핑 내용·설정 값은 알림에 넣지 않는다.
"""
import json
import logging
import os
import sys
import urllib.request
from datetime import date, datetime, time, timedelta
from pathlib import Path

from sqlalchemy import select

import db
from pipeline import deliver, run_daily

log = logging.getLogger("toolscout.watchdog")

HEALTH_URL = "http://127.0.0.1:8000/api/health"
GRACE = timedelta(minutes=30)
ACTIVE_FROM, ACTIVE_UNTIL = time(6, 0), time(22, 0)
STATE_PATH = Path(os.environ.get("LOCALAPPDATA", ".")) / "toolscout" / "watchdog.json"


def app_up(url: str = HEALTH_URL) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status == 200
    except OSError:
        return False


def mail_status(day: date) -> list[dict]:
    """대상 사용자(데모 제외)마다 {user_id, notify_time, has_briefing, sent}."""
    targets = set(run_daily.target_user_ids())
    with db.session() as s:
        users = s.exec(select(db.User.id, db.User.notify_time).where(db.User.id.in_(targets), db.User.is_demo == False)).all()  # noqa: E712
        rows = s.exec(select(db.Briefing.user_id, db.Briefing.sent_at).where(db.Briefing.date == day)).all()
    has, sent = {uid for uid, _ in rows}, {uid for uid, at in rows if at is not None}
    return [{"user_id": uid, "notify_time": nt, "has_briefing": uid in has, "sent": uid in sent} for uid, nt in users]


def problems(now: datetime, up: bool, status: list[dict] | None) -> dict[str, list[str]]:
    """{문제 종류: 알림 본문 줄}. status가 None이면 DB를 못 읽은 것."""
    if not ACTIVE_FROM <= now.time() < ACTIVE_UNTIL:
        return {}
    found: dict[str, list[str]] = {}
    if not up:
        found["app_down"] = [f"{now:%H:%M}에 앱(8000번 포트)이 응답하지 않아요.",
                             "PC가 켜져 있다면 작업 스케줄러의 'toolscout app'과 %LOCALAPPDATA%\\toolscout\\app.log를 봐 주세요."]
    if status is None:
        found["db_error"] = ["DB(Supabase)에서 오늘 발송 기록을 읽지 못했어요. 연결이나 일시 중지 상태를 봐 주세요."]
        return found
    due = [u for u in status if datetime.combine(now.date(), time.fromisoformat(u["notify_time"]), now.tzinfo) + GRACE <= now]
    no_run = [u for u in due if not u["has_briefing"]]
    no_send = [u for u in due if u["has_briefing"] and not u["sent"]]
    if no_run:
        found["no_briefing"] = [f"알림 시각이 지났는데 오늘 브리핑이 아예 없는 사용자 {len(no_run)}명 (하루 실행 문제).",
                                "앱이 떠 있으면 22:00 전까지 스스로 따라잡아요. 계속 없으면 GET /api/w1/status를 봐 주세요."]
    if no_send:
        found["not_sent"] = [f"브리핑은 만들어졌는데 아직 메일이 안 나간 사용자 {len(no_send)}명 (발송 문제).",
                             "메일 설정(GMAIL_*)과 app.log의 발송 기록을 봐 주세요. 다음 알림 시각이나 재시작 때 다시 보내요."]
    return found


def run(now: datetime | None = None, up_fn=app_up, status_fn=mail_status, alert_fn=deliver.send_alert,
        state_path: Path | None = None) -> dict:
    path = state_path or STATE_PATH
    now = now or datetime.now(run_daily.KST)
    up = up_fn()
    try:
        status = status_fn(now.date())
    except Exception as exc:  # DB 오류도 알릴 거리다
        log.warning("발송 기록 조회 실패(%s)", type(exc).__name__)
        status = None
    found = problems(now, up, status)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    today = state.get(str(now.date()), [])
    new = {k: v for k, v in found.items() if k not in today}
    alert = None
    if new:
        lines = [line for v in new.values() for line in v]
        alert = alert_fn(f"{now:%m월 %d일} 앱 바깥 감시: {len(new)}건", lines)
        if alert == "sent":
            state = {str(now.date()): today + list(new)}  # 지난 날짜 기록은 버린다
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state), encoding="utf-8")
    result = {"at": now.isoformat(timespec="minutes"), "app_up": up, "problems": sorted(found), "alerted": sorted(new), "alert": alert}
    log.warning("감시 결과 %s", json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    print(json.dumps(run(), ensure_ascii=False))
    sys.exit(0)
