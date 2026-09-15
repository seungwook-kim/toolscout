"""앱 안 예약 검수 (계획안 9.2 W1, 2026-09-15 n8n 제외 결정). 가짜 시계·가짜 실행·가짜 발송으로 확인한다.

실행: uv run python -m tests.pipeline.check_scheduler
- 06:50 → 다음 예정 06:55 / 06:55 예열 → 07:00 하루 실행 → 08·09·12·18시 발송 → 다음 날 06:55
- 07:30에 켜지면 브리핑 없는 사용자가 있을 때만 바로 따라잡고, 08:05에 켜지면 바로 발송, 22:00 뒤에는 따라잡지 않음
- 08:00에 실행이 돌고 있으면 끝난 뒤 발송, 실행 중 중복 실행은 막음
- 발송 실패 사용자는 10분 간격으로 2번 더, 메일 설정이 없으면 다시 시도하지 않음
DB·모델·메일을 쓰지 않는다.
"""
import asyncio
import json
import sys
from datetime import date, datetime, timedelta

from pipeline import run_daily
from pipeline.scheduler import RETRY_WAIT_SECONDS, Scheduler

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


def make(clock: Clock, *, needs: bool = True, gate: asyncio.Event | None = None, send_results: list[dict] | None = None):
    log: list[str] = []
    results = list(send_results or [])

    async def run(users=None, limit=None, user_ids=None):
        log.append(f"run@{clock.now():%H:%M}")
        if gate is not None:  # 검수가 풀어 줄 때까지 실행이 돌고 있는 상태
            await gate.wait()
            log.append("run_done")
        return {"date": str(clock.now().date()), "totals": {"cards": 3}, "all_users_failed": False, "trace_url": None}

    def send(day, until=None):
        log.append(f"send@{clock.now():%H:%M}")
        return results.pop(0) if results else {"mode": "smtp", "sent": [1], "failed": []}

    async def needs_run(day):
        return needs

    def warm():
        log.append(f"warm@{clock.now():%H:%M}")
        return [{"model": "local", "ok": True}]

    return Scheduler(run=run, send=send, warm=warm, needs_run=needs_run, now=clock.now, sleep=clock.sleep), log


async def normal_day() -> dict:
    clock = Clock(6, 50)
    sched, log = make(clock)
    before = sched.next_event()
    for _ in range(5000):  # 루프: 06:50 → 06:55 예열 → 07:00 실행 → 08·09·12·18시 발송 → 다음 날 대기
        await sched.tick()
        if len(sched.state["sent_slots"].get(DAY, ())) == 4:
            break
        await clock.sleep(max(1.0, min((sched.next_event() - clock.now()).total_seconds(), 60)))
    after = sched.next_event()
    return {"before": before, "after": after, "log": log}


async def main_async() -> dict:
    day = await normal_day()

    late = Clock(7, 30)
    s_late, log_late = make(late, needs=True)
    await s_late.tick()

    done_already = Clock(7, 30)
    s_done, log_done = make(done_already, needs=False)
    await s_done.tick()

    after_send_time = Clock(8, 5)
    s_after, log_after = make(after_send_time, needs=False)
    await s_after.tick()

    night = Clock(22, 30)
    s_night, log_night = make(night, needs=True)
    await s_night.tick()

    busy = Clock(7, 55)
    gate = asyncio.Event()
    s_busy, log_busy = make(busy, gate=gate)
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
    failing = [{"mode": "smtp", "sent": [], "failed": [{"user_id": 2, "error": "x"}]}] * 3
    s_retry, log_retry = make(retry_clock, send_results=failing)
    retried = await s_retry.send_now(DAY)

    missing_clock = Clock(8, 0)
    s_missing, log_missing = make(missing_clock, send_results=[{"mode": "config_missing", "sent": [], "failed": [{"user_id": 1, "error": "x"}]}])
    await s_missing.send_now(DAY)

    checks = {
        "06:50엔_다음예정_06:55": day["before"] == datetime(2026, 9, 16, 6, 55, tzinfo=run_daily.KST),
        "06:55_예열_07:00_실행_알림시각마다_발송": day["log"] == ["warm@06:55", "run@07:00", "send@08:00", "send@09:00",
                                                         "send@12:00", "send@18:00"],
        "발송뒤_다음예정_다음날_06:55": day["after"] == datetime(2026, 9, 17, 6, 55, tzinfo=run_daily.KST),
        "07시_뒤에_켜지면_예열_안함": not any(x.startswith("warm") for x in log_late + log_after),
        "07:30_켜지면_따라잡기": log_late == ["run@07:30"],
        "이미_브리핑있으면_실행안함": log_done == [],
        "08:05_켜지면_08시_몫만_바로_발송": log_after == ["send@08:05"],
        "22시_뒤엔_따라잡지_않음": log_night == [],
        "실행중_중복실행_막음": duplicate == {"status": "running"},
        "실행_끝난뒤_발송": not sent_while_running and log_busy == ["run@07:55", "run_done", "send@07:55"],
        "발송실패_10분간격_2번더": log_retry == ["send@08:00", "send@08:10", "send@08:20"]
        and len(retried["attempts"]) == 3 and retry_clock.naps == [RETRY_WAIT_SECONDS] * 2,
        "메일설정_없으면_재시도안함": log_missing == ["send@08:00"],
    }
    return {"normal_day": {"log": day["log"]}, "busy": log_busy, "retry": log_retry, "checks": checks}


def main() -> int:
    report = asyncio.run(main_async())
    report["pass"] = all(report["checks"].values())
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
