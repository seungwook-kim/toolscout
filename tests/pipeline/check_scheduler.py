"""앱 안 예약 검수 (계획안 9.2 W1·W4, 2026-09-15 n8n 제외 결정). 가짜 시계·가짜 실행·가짜 발송·가짜 알림으로 확인한다.

실행: uv run python -m tests.pipeline.check_scheduler
- 06:50 → 다음 예정 06:55 / 06:55 예열·DB 깨우기 → 07:00 하루 실행 → 08·09·12·18시 발송 → 다음 날 06:55
- 07:30에 켜지면 브리핑 없는 사용자가 있을 때만 바로 따라잡고, 08:05에 켜지면 바로 발송, 22:00 뒤에는 따라잡지 않음
- 08:00에 실행이 돌고 있으면 끝난 뒤 발송, 실행 중 중복 실행은 막음
- 발송 실패 사용자는 10분 간격으로 2번 더, 끝내 실패하면 실패 알림 한 통(같은 시각 두 번째는 알림 안 함), 메일 설정이 없으면 재시도·알림 안 함
- 하루 실행 실패는 30분 간격으로 2번 더 → 그래도 실패면 실패 알림 한 통, 그날 더 시도 안 함
- 일부 사용자만 빠지면 그 사용자만 다시 / DB 연결 실패도 30분 뒤 다시(1분마다 반복 안 함) / "지금 만들기"가 돌고 있으면 끝난 뒤 다시(시도 횟수에 안 셈)
DB·모델·메일을 쓰지 않는다.
"""
import asyncio
import json
import sys
from datetime import date, datetime, timedelta

from pipeline import run_daily
from pipeline.scheduler import RETRY_WAIT_SECONDS, RUN_RETRY_WAIT_SECONDS, Scheduler

DAY = date(2026, 9, 16)


class Clock:
    def __init__(self, hour: int, minute: int = 0):
        self.value = datetime(DAY.year, DAY.month, DAY.day, hour, minute, tzinfo=run_daily.KST)
        self.naps: list[float] = []

    def now(self) -> datetime:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.naps.append(seconds)
        self.value += timedelta(seconds=seconds)
        await asyncio.sleep(0)


def make(clock: Clock, *, needs: bool = True, gate: asyncio.Event | None = None, send_results: list[dict] | None = None,
         run_outcomes: list[dict] | None = None, db_errors: int = 0):
    """run_outcomes: 실행마다 {"raise": True} 또는 {"leave": [끝나고도 브리핑 없는 사용자]}. 기본은 전원 성공."""
    log: list[str] = []
    results = list(send_results or [])
    outcomes = list(run_outcomes or [])
    fake = {"missing": [1, 2] if needs else [], "db_errors": db_errors, "run_users": [], "alerts": []}

    async def run(users=None, limit=None, user_ids=None):
        log.append(f"run@{clock.now():%H:%M}")
        fake["run_users"].append(user_ids)
        if gate is not None:  # 검수가 풀어 줄 때까지 실행이 돌고 있는 상태
            await gate.wait()
            log.append("run_done")
        outcome = outcomes.pop(0) if outcomes else {}
        if outcome.get("raise"):
            raise RuntimeError("검수용 실행 실패")
        fake["missing"] = list(outcome.get("leave", []))
        return {"date": str(clock.now().date()), "totals": {"cards": 3}, "all_users_failed": False, "trace_url": None}

    def send(day, until=None):
        log.append(f"send@{clock.now():%H:%M}")
        return results.pop(0) if results else {"mode": "smtp", "sent": [1], "failed": []}

    async def missing_users(day):
        if fake["db_errors"]:
            fake["db_errors"] -= 1
            log.append(f"db_error@{clock.now():%H:%M}")
            raise ConnectionError("검수용 DB 연결 실패")
        return list(fake["missing"])

    def warm():
        log.append(f"warm@{clock.now():%H:%M}")
        return [{"model": "local", "ok": True}]

    def wake_db():
        log.append(f"wake@{clock.now():%H:%M}")

    def alert(title, lines):
        log.append(f"alert@{clock.now():%H:%M}")
        fake["alerts"].append({"title": title, "lines": lines})
        return "sent"

    sched = Scheduler(run=run, send=send, warm=warm, wake_db=wake_db, missing_users=missing_users, alert=alert,
                      now=clock.now, sleep=clock.sleep)
    return sched, log, fake


async def drive(sched: Scheduler, clock: Clock, until: datetime) -> None:
    """예약 루프처럼 tick → 다음 예정까지(최대 60초) 잠들기를 until까지 반복한다."""
    while clock.now() < until:
        await sched.tick()
        await clock.sleep(max(1.0, min((sched.next_event() - clock.now()).total_seconds(), 60)))


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(DAY.year, DAY.month, DAY.day, hour, minute, tzinfo=run_daily.KST)


async def normal_day() -> dict:
    clock = Clock(6, 50)
    sched, log, _ = make(clock)
    before = sched.next_event()
    for _ in range(5000):  # 루프: 06:50 → 06:55 예열 → 07:00 실행 → 08·09·12·18시 발송 → 다음 날 대기
        await sched.tick()
        if len(sched.state["sent_slots"].get(DAY, ())) == 4:
            break
        await clock.sleep(max(1.0, min((sched.next_event() - clock.now()).total_seconds(), 60)))
    after = sched.next_event()
    return {"before": before, "after": after, "log": log, "warm": sched.state["last_warm"]}


async def main_async() -> dict:
    day = await normal_day()

    late = Clock(7, 30)
    s_late, log_late, _ = make(late, needs=True)
    await s_late.tick()

    done_already = Clock(7, 30)
    s_done, log_done, _ = make(done_already, needs=False)
    await s_done.tick()

    after_send_time = Clock(8, 5)
    s_after, log_after, _ = make(after_send_time, needs=False)
    await s_after.tick()

    night = Clock(22, 30)
    s_night, log_night, _ = make(night, needs=True)
    await s_night.tick()

    busy = Clock(7, 55)
    gate = asyncio.Event()
    s_busy, log_busy, _ = make(busy, gate=gate)
    run_task = asyncio.create_task(s_busy.run_now())
    await asyncio.sleep(0)
    duplicate = await s_busy.run_now()
    send_task = asyncio.create_task(s_busy.send_now(DAY))
    for _ in range(5):
        await asyncio.sleep(0)
    sent_while_running = any(entry.startswith("send") for entry in log_busy)
    gate.set()
    await asyncio.gather(run_task, send_task)

    retry_clock = Clock(8, 0)
    failing = [{"mode": "smtp", "sent": [], "failed": [{"user_id": 2, "error": "x"}]}] * 6
    s_retry, log_retry, fake_retry = make(retry_clock, send_results=failing)
    retried = await s_retry.send_now(DAY, "08:00")
    await s_retry.send_now(DAY, "08:00")  # 같은 시각 두 번째 실패는 알림을 또 보내지 않는다

    missing_clock = Clock(8, 0)
    s_missing, log_missing, fake_missing = make(missing_clock, send_results=[{"mode": "config_missing", "sent": [], "failed": [{"user_id": 1, "error": "x"}]}])
    await s_missing.send_now(DAY)

    fail_clock = Clock(7, 0)
    s_fail, log_fail, fake_fail = make(fail_clock, run_outcomes=[{"raise": True}] * 5)
    await s_fail.tick()
    next_after_fail = s_fail.next_event()
    await drive(s_fail, fail_clock, at(12, 30))

    partial_clock = Clock(7, 0)
    s_partial, log_partial, fake_partial = make(partial_clock, run_outcomes=[{"leave": [2]}, {}])
    await drive(s_partial, partial_clock, at(7, 45))

    db_clock = Clock(7, 0)
    s_db, log_db, _ = make(db_clock, db_errors=1)
    await drive(s_db, db_clock, at(7, 45))

    manual_clock = Clock(7, 0)
    s_manual, log_manual, _ = make(manual_clock)
    await s_manual._run_lock.acquire()  # "지금 만들기"가 돌고 있는 상태
    await s_manual.tick()
    retry_after_manual = s_manual.state["run_retry_at"]
    s_manual._run_lock.release()
    await drive(s_manual, manual_clock, at(7, 5))

    run_entries = lambda log: [x for x in log if x.startswith(("run@", "alert@", "db_error@"))]  # noqa: E731
    checks = {
        "06:50엔_다음예정_06:55": day["before"] == at(6, 55),
        "06:55_예열·DB깨우기_07:00_실행_알림시각마다_발송": day["log"] == ["warm@06:55", "wake@06:55", "run@07:00", "send@08:00",
                                                               "send@09:00", "send@12:00", "send@18:00"]
        and day["warm"]["db"] == "ok",
        "발송뒤_다음예정_다음날_06:55": day["after"] == datetime(2026, 9, 17, 6, 55, tzinfo=run_daily.KST),
        "07시_뒤에_켜지면_예열_안함": not any(x.startswith(("warm", "wake")) for x in log_late + log_after),
        "07:30_켜지면_따라잡기": log_late == ["run@07:30"],
        "이미_브리핑있으면_실행안함": log_done == [],
        "08:05_켜지면_08시_몫만_바로_발송": log_after == ["send@08:05"],
        "22시_뒤엔_따라잡지_않음": log_night == [],
        "실행중_중복실행_막음": duplicate == {"status": "running"},
        "실행_끝난뒤_발송": not sent_while_running and log_busy == ["run@07:55", "run_done", "send@07:55"],
        "발송실패_10분간격_2번더": log_retry[:3] == ["send@08:00", "send@08:10", "send@08:20"]
        and len(retried["attempts"]) == 3 and retry_clock.naps[:2] == [RETRY_WAIT_SECONDS] * 2,
        "발송_끝내실패면_알림_한번": [x for x in log_retry if x.startswith("alert")] == ["alert@08:20"]
        and "발송 실패" in fake_retry["alerts"][0]["title"] and s_retry.status()["alerts"] == {str(DAY): {"send:08:00": "sent"}},
        "메일설정_없으면_재시도·알림안함": log_missing == ["send@08:00"] and fake_missing["alerts"] == [],
        "실행실패_30분간격_2번더_뒤_알림_한번": run_entries(log_fail) == ["run@07:00", "run@07:30", "run@08:00", "alert@08:00"]
        and s_fail.state["run_checked"] == DAY and "마지막 오류 종류: RuntimeError" in fake_fail["alerts"][0]["lines"],
        "재시도_예정이_다음예정에_보임": next_after_fail == at(7, 0) + timedelta(seconds=RUN_RETRY_WAIT_SECONDS),
        "일부_사용자만_빠지면_그_사용자만_다시": run_entries(log_partial) == ["run@07:00", "run@07:30"]
        and fake_partial["run_users"] == [[1, 2], [2]] and fake_partial["alerts"] == [],
        "DB연결실패도_30분뒤_다시(1분마다_반복안함)": run_entries(log_db) == ["db_error@07:00", "run@07:30"],
        "지금만들기_중이면_끝난뒤_다시·횟수안셈": retry_after_manual == at(7, 1) and log_manual == ["run@07:01"]
        and s_manual.state["run_attempts"][DAY] == 1,
        "알림에_설정값·오류원문_없음": all("검수용" not in line for alert in fake_fail["alerts"] + fake_retry["alerts"]
                                     for line in alert["lines"]),
    }
    return {"normal_day": {"log": day["log"]}, "busy": log_busy, "retry": log_retry, "run_fail": run_entries(log_fail),
            "partial": fake_partial["run_users"], "db": log_db, "checks": checks}


def main() -> int:
    report = asyncio.run(main_async())
    report["pass"] = all(report["checks"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
