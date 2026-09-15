"""앱 안 예약 작업 (계획안 9.2 W1). 개발 중에는 FastAPI 앱이 떠 있는 동안 여기서 돌고, 배포 단계에서 n8n 크론이 /api/w1/run을 부르는 형태로 바꾼다 (2026-09-15 사용자 결정).

- 매일 06:55 KST 로컬 모델 예열(models.warm_local), 07:00 하루 실행(run_daily.run), 08:00 발송(deliver.send_day)
- 07:00에 앱이 꺼져 있었으면 그날 22:00 전에 켜질 때 바로 따라잡는다. 대상 사용자 중 그날 briefings가 없는 사람이 있을 때만
- 08:00에 하루 실행이 돌고 있으면 끝날 때까지 기다렸다 보낸다. 발송은 sent_at 기준 멱등이라 다시 불러도 안전하다
- 발송 실패 사용자가 있으면 10분 간격으로 2번 더 보낸다
- 절전으로 시계가 건너뛰어도 늦게라도 돌도록 최대 60초마다 벽시계를 다시 본다
- 상태(다음 예정·마지막 실행·마지막 발송)는 GET /api/w1/status. SCHEDULER_ENABLED=0이면 켜지 않는다 (검수 서버)
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable

import models
from pipeline import deliver, persist, run_daily

log = logging.getLogger("toolscout.scheduler")

WARM_AT, RUN_AT, SEND_AT, CATCH_UP_UNTIL = time(6, 55), time(7, 0), time(8, 0), time(22, 0)
SEND_RETRIES, RETRY_WAIT_SECONDS, MAX_NAP_SECONDS = 2, 600, 60


def enabled() -> bool:
    return os.environ.get("SCHEDULER_ENABLED", "1").strip() != "0"


async def _needs_run(day: date) -> bool:
    targets = await asyncio.to_thread(run_daily.target_user_ids)
    done = await asyncio.to_thread(persist.users_with_briefings, day)
    return any(uid not in done for uid in targets)


@dataclass
class Scheduler:
    run: Callable[..., Awaitable[dict]] = run_daily.run
    send: Callable[[date], Any] = deliver.send_day
    warm: Callable[[], Any] = models.warm_local
    needs_run: Callable[[date], Awaitable[bool]] = _needs_run
    now: Callable[[], datetime] = lambda: datetime.now(run_daily.KST)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    state: dict = field(default_factory=lambda: {"last_run": None, "last_send": None, "last_warm": None,
                                                 "warm_done": None, "run_checked": None, "send_done": None})
    _run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _task: asyncio.Task | None = None

    def running(self) -> bool:
        return self._run_lock.locked()

    async def run_now(self, users: int | None = None, limit: int | None = None) -> dict:
        """하루 실행. 이미 돌고 있으면 {"status": "running"}."""
        if self._run_lock.locked():
            return {"status": "running"}
        async with self._run_lock:
            started = self.now()
            try:
                report = await self.run(users=users, limit=limit)
                summary = {"status": "done", "date": report["date"], "totals": report["totals"],
                           "exit_code": run_daily.exit_code(report), "trace_url": report.get("trace_url"),
                           "source_failures": report.get("source_failures", [])}
            except Exception as exc:  # 실패도 상태로 남긴다. 다음 날 예약은 계속 돈다
                log.exception("하루 실행 실패")
                summary = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}", "exit_code": 1}
            self.state["last_run"] = summary | {"started_at": started.isoformat(), "finished_at": self.now().isoformat()}
            return self.state["last_run"]

    async def send_now(self, day: date | None = None) -> dict:
        """발송. 하루 실행이 돌고 있으면 끝날 때까지 기다린다. 실패 사용자는 10분 간격으로 2번 더."""
        day = day or self.now().date()
        async with self._run_lock:  # 실행 중이면 여기서 기다린다
            pass
        attempts = []
        for attempt in range(SEND_RETRIES + 1):
            result = await asyncio.to_thread(self.send, day)
            attempts.append({"attempt": attempt + 1, "mode": result["mode"], "sent": result["sent"], "failed": result["failed"]})
            if not result["failed"] or result["mode"] == "config_missing":
                break
            if attempt < SEND_RETRIES:
                await self.sleep(RETRY_WAIT_SECONDS)
        self.state["last_send"] = {"date": str(day), "attempts": attempts, "finished_at": self.now().isoformat(),
                                   "failed": attempts[-1]["failed"]}
        return self.state["last_send"]

    async def tick(self) -> None:
        """지금 시각에 할 일을 한다. 루프가 매번 부른다."""
        now = self.now()
        today = now.date()
        if WARM_AT <= now.time() < RUN_AT and self.state["warm_done"] != today:
            self.state["last_warm"] = {"results": await asyncio.to_thread(self.warm), "at": self.now().isoformat()}
            self.state["warm_done"] = today
        if RUN_AT <= now.time() < CATCH_UP_UNTIL and self.state["run_checked"] != today:
            if await self.needs_run(today):
                await self.run_now()
            self.state["run_checked"] = today
        if SEND_AT <= now.time() < CATCH_UP_UNTIL and self.state["send_done"] != today:
            await self.send_now(today)
            self.state["send_done"] = today

    def next_event(self) -> datetime:
        now = self.now()
        today = now.date()
        candidates = []
        if self.state["warm_done"] != today:
            candidates.append(datetime.combine(today, WARM_AT, now.tzinfo))
        if self.state["run_checked"] != today:
            candidates.append(datetime.combine(today, RUN_AT, now.tzinfo))
        if self.state["send_done"] != today:
            candidates.append(datetime.combine(today, SEND_AT, now.tzinfo))
        candidates = [c for c in candidates if c > now] or [datetime.combine(today + timedelta(days=1), WARM_AT, now.tzinfo)]
        return min(candidates)

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # 예약 루프는 죽지 않는다
                log.exception("예약 작업 실패")
            wait = (self.next_event() - self.now()).total_seconds()
            await self.sleep(max(1.0, min(wait, MAX_NAP_SECONDS)))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.loop())
            log.warning("예약 작업 시작: 매일 %s 예열, %s 하루 실행, %s 발송 (KST)", WARM_AT.strftime("%H:%M"), RUN_AT.strftime("%H:%M"),
                        SEND_AT.strftime("%H:%M"))

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def status(self) -> dict:
        return {"enabled": self._task is not None and not self._task.done(), "running": self.running(),
                "next_event": self.next_event().isoformat(), **{k: self.state[k] for k in ("last_warm", "last_run", "last_send")}}


scheduler = Scheduler()
