"""앱 바깥 감시 검수 (2026-09-23). 가짜 시계·가짜 앱 상태·가짜 발송 기록·가짜 알림으로 확인한다.

실행: uv run python -m tests.pipeline.check_watchdog
- 정상(앱 응답·알림 시각 지난 사용자 모두 발송)이면 알림 없음
- 앱 무응답 / 브리핑 없음(실행 문제) / 브리핑 있는데 미발송(발송 문제) / DB 조회 실패를 각각 알림
- 알림 시각 + 30분 전에는 발송 여부를 보지 않음, 06:00 전·22:00 뒤에는 아무것도 안 봄
- 같은 날 같은 문제는 한 번만, 새 문제는 따로 한 번, 다음 날은 다시 / 알림을 못 보냈으면 기록하지 않아 다음 확인에 다시
- 실제 DB에서 오늘 발송 기록을 읽는다(읽기만)
메일을 보내지 않는다.
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from pipeline import run_daily, watchdog

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


def at(hour: int, minute: int = 0, day: int = 24) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=run_daily.KST)


def user(notify="08:00", has=True, sent=True):
    return {"user_id": 45, "notify_time": notify, "has_briefing": has, "sent": sent}


def P(now, up=True, status=None):
    return sorted(watchdog.problems(now, up, [user()] if status is None else status))


check("정상이면 문제 없음", P(at(8, 30)) == [])
check("앱 무응답", P(at(8, 30), up=False) == ["app_down"])
check("브리핑 없음 → 실행 문제", P(at(8, 30), status=[user(has=False, sent=False)]) == ["no_briefing"])
check("브리핑 있는데 미발송 → 발송 문제", P(at(8, 30), status=[user(sent=False)]) == ["not_sent"])
check("알림 시각 + 30분 전에는 발송 여부 안 봄", P(at(8, 29), status=[user(sent=False)]) == []
      and P(at(12, 30), status=[user("12:00", sent=False)]) == ["not_sent"] and P(at(9, 30), status=[user("12:00", has=False, sent=False)]) == [])
check("DB 조회 실패", sorted(watchdog.problems(at(8, 30), True, None)) == ["db_error"])
check("06:00 전·22:00 뒤에는 안 봄", P(at(5, 59), up=False) == [] and P(at(22, 0), up=False) == [] and P(at(6, 0), up=False) == ["app_down"])

state = Path(tempfile.mkdtemp()) / "watchdog.json"
sent = []


def run(now, up=True, status=None, alert="sent"):
    return watchdog.run(now, up_fn=lambda: up, status_fn=lambda d: [user()] if status is None else status,
                        alert_fn=lambda title, lines: sent.append((title, lines)) or alert, state_path=state)


r1 = run(at(8, 30), up=False)
r2 = run(at(9, 30), up=False)
check("같은 날 같은 문제는 한 번만", r1["alerted"] == ["app_down"] and r2["alerted"] == [] and len(sent) == 1)
r3 = run(at(12, 30), up=False, status=[user(sent=False)])
check("새 문제는 따로 한 번", r3["alerted"] == ["not_sent"] and len(sent) == 2)
r4 = run(at(8, 30, day=25), up=False)
check("다음 날은 다시", r4["alerted"] == ["app_down"] and len(sent) == 3)
r5 = run(at(9, 30, day=25), status=[user(has=False, sent=False)], alert="mail_error")
r6 = run(at(12, 30, day=25), status=[user(has=False, sent=False)])
check("알림 못 보냈으면 다음 확인에 다시", r5["alerted"] == ["no_briefing"] and r6["alerted"] == ["no_briefing"] and len(sent) == 5)
r7 = run(at(8, 30, day=26), status=None)
r8 = watchdog.run(at(8, 30, day=26), up_fn=lambda: True, status_fn=lambda d: 1 / 0, alert_fn=lambda t, l: "sent", state_path=state)
check("정상이면 알림 안 보냄, 조회 예외는 db_error", r7["alerted"] == [] and r8["alerted"] == ["db_error"])
title, lines = sent[0]
check("알림 본문에 브리핑 내용·설정 값 없음", "앱 바깥 감시" in title and not any("@" in line or "http" in line for line in lines))

try:
    status = watchdog.mail_status(datetime.now(run_daily.KST).date())
    check("실제 DB에서 오늘 발송 기록을 읽음", isinstance(status, list) and all({"user_id", "notify_time", "has_briefing", "sent"} <= set(u) for u in status))
except Exception as exc:  # noqa: BLE001
    check(f"실제 DB에서 오늘 발송 기록을 읽음 ({type(exc).__name__})", False)

passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
