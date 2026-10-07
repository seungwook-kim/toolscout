"""앱 안 예약 작업 (계획안 9.2 W1). 개발 중에는 FastAPI 앱이 떠 있는 동안 여기서 돌고, 배포 단계에서 n8n 크론이 /api/w1/run을 부르는 형태로 바꾼다 (2026-09-15 사용자 결정).

- 매일 06:00 KST 검증(W1-a, agent/verifier.run: 전날 검증 요청 + 미완료 재시도), 06:55 로컬 모델 예열(models.warm_local), 07:00 하루 실행(run_daily.run),
  알림 시각(08:00·09:00·12:00·18:00)마다 그 시각까지로 고른 사용자에게 발송(deliver.send_day)
- 07:00에 앱이 꺼져 있었으면 그날 22:00 전에 켜질 때 바로 따라잡는다. 대상 사용자 중 그날 briefings가 없는 사람이 있을 때만
- 08:00에 하루 실행이 돌고 있으면 끝날 때까지 기다렸다 보낸다. 발송은 sent_at 기준 멱등이라 다시 불러도 안전하다
- 발송 실패 사용자가 있으면 10분 간격으로 2번 더 보낸다
- 하루 실행이 실패하거나 브리핑 없는 대상 사용자가 남으면 30분 뒤 그 사용자만 다시, 2번까지 (계획안 "W1이 죽고 재실행", 부록 B 모델 장애)
- 재실행까지 실패하거나 발송이 끝내 실패하면 ADMIN_EMAILS에 실패 알림 한 통 (계획안 W4). 같은 날 같은 일은 한 번만
- 06:55 예열 때 DB에 한 번 접속한다 (Supabase 깨우기, 계획안 W4)
- 검증은 따로 도는 작업이라 예열·실행·발송을 막지 않는다. 06:00 뒤에 켜지면 07:00 전이거나 그날 하루 실행이 끝난 뒤 한 번. 실패해도 다시 안 돌고
  미완료 요청은 다음 날 06:00이 다시 꺼낸다 (세션 8, 계획안 조정 "검증관 크론은 W1과 분리")
- 월요일에는 하루 실행 전에 주간 기억 합치기(memory.merge_weights). 06:55 뒤에 켜져도 그날 실행 전에 한 번 (계획안 W4)
- 절전으로 시계가 건너뛰어도 늦게라도 돌도록 최대 60초마다 벽시계를 다시 본다
- 할 일을 마칠 때마다 main 커밋이 바뀌었는지 보고, 한가하면 스스로 꺼져 런처가 새 코드로 다시 띄운다 (pipeline/autorestart.py)
- 상태(다음 예정·마지막 실행·마지막 발송)는 GET /api/w1/status. SCHEDULER_ENABLED=0이면 켜지 않는다 (검수 서버)
"""
import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Awaitable, Callable

import memory
import models
from memory import NOTIFY_TIMES
from agent import tracing, verifier
from pipeline import autorestart, deliver, persist, run_daily

log = logging.getLogger("toolscout.scheduler")

VERIFY_AT, WARM_AT, RUN_AT, CATCH_UP_UNTIL = time(6, 0), time(6, 55), time(7, 0), time(22, 0)
SEND_SLOTS = [time.fromisoformat(t) for t in NOTIFY_TIMES]  # 사용자 설정 알림 시각
SEND_RETRIES, RETRY_WAIT_SECONDS, MAX_NAP_SECONDS = 2, 600, 60
RUN_RETRIES, RUN_RETRY_WAIT_SECONDS = 2, 1800  # 하루 실행 재시도 (2026-09-15 기본값, 계획안에 횟수 없음)


def external() -> bool:
    """JOBS_EXTERNAL=1이면 예약 작업이 앱 밖(Railway 크론, pipeline/cron.py)에서 돈다. 웹(Vercel)은 하루 실행을 직접 돌리지 않고
    "지금 만들기"는 요청만 남기며, /api/w1 실행·발송은 409로 막는다 (2026-10-07 사용자 결정 "vercel + railway")."""
    return os.environ.get("JOBS_EXTERNAL", "0").strip() == "1"


def enabled() -> bool:
    return os.environ.get("SCHEDULER_ENABLED", "1").strip() != "0"


async def _missing_users(day: date) -> list[int]:
    """대상 사용자 중 그날 briefings 행(카드 또는 빈 행)이 없는 사람. 모델 장애로 빠진 사용자도 여기 남는다."""
    targets = await asyncio.to_thread(run_daily.target_user_ids)
    done = await asyncio.to_thread(persist.users_with_briefings, day)
    return [uid for uid in targets if uid not in done]


async def _verify(day: date) -> dict:
    return await verifier.run(day=day)


@dataclass
class Scheduler:
    run: Callable[..., Awaitable[dict]] = run_daily.run
    send: Callable[..., Any] = deliver.send_day
    verify: Callable[[date], Awaitable[dict]] = _verify
    warm: Callable[[], Any] = models.warm_local
    wake_db: Callable[[], Any] = persist.wake_db
    merge: Callable[[date], Any] = memory.merge_weights
    missing_users: Callable[[date], Awaitable[list[int]]] = _missing_users
    alert: Callable[[str, list[str]], str] = deliver.send_alert
    now: Callable[[], datetime] = lambda: datetime.now(run_daily.KST)
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    state: dict = field(default_factory=lambda: {"last_run": None, "last_send": None, "last_warm": None,
                                                 "warm_done": None, "run_checked": None, "sent_slots": {},
                                                 "run_attempts": {}, "run_retry_at": None, "alerts": {},
                                                 "merge_done": None, "last_merge": None, "verify_done": None, "last_verify": None})
    _run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _task: asyncio.Task | None = None
    _verify_task: asyncio.Task | None = None
    _restart: autorestart.AutoRestart | None = None

    def running(self) -> bool:
        return self._run_lock.locked()

    async def run_now(self, users: int | None = None, limit: int | None = None, user_ids: list[int] | None = None) -> dict:
        """하루 실행. 이미 돌고 있으면 {"status": "running"}."""
        if self._run_lock.locked():
            return {"status": "running"}
        async with self._run_lock:
            started = self.now()
            try:
                report = await self.run(users=users, limit=limit, user_ids=user_ids)
                summary = {"status": "done", "date": report["date"], "totals": report["totals"],
                           "exit_code": run_daily.exit_code(report), "trace_url": report.get("trace_url"),
                           "source_failures": report.get("source_failures", [])}
            except Exception as exc:  # 실패도 상태로 남긴다. 다음 날 예약은 계속 돈다
                log.exception("하루 실행 실패")
                summary = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:300]}", "exit_code": 1}
            self.state["last_run"] = summary | {"started_at": started.isoformat(), "finished_at": self.now().isoformat()}
            return self.state["last_run"]

    async def send_now(self, day: date | None = None, until: str | None = None) -> dict:
        """발송. until이 있으면 알림 시각이 그때까지인 사용자만. 하루 실행이 돌고 있으면 끝날 때까지 기다린다. 실패는 10분 간격 2번 더."""
        day = day or self.now().date()
        async with self._run_lock:  # 실행 중이면 여기서 기다린다
            pass
        attempts = []
        for attempt in range(SEND_RETRIES + 1):
            result = await asyncio.to_thread(self.send, day, until)
            attempts.append({"attempt": attempt + 1, "mode": result["mode"], "sent": result["sent"], "failed": result["failed"]})
            if not result["failed"] or result["mode"] == "config_missing":
                break
            if attempt < SEND_RETRIES:
                await self.sleep(RETRY_WAIT_SECONDS)
        self.state["last_send"] = {"date": str(day), "until": until, "attempts": attempts, "finished_at": self.now().isoformat(),
                                   "failed": attempts[-1]["failed"]}
        if attempts[-1]["failed"] and attempts[-1]["mode"] != "config_missing":  # 메일 설정이 없으면 알림 메일도 못 보낸다
            await self._alert(day, f"send:{until}", f"{day:%m월 %d일} 발송 실패", [
                f"알림 시각 {until or '전체'} 발송에서 {len(attempts[-1]['failed'])}명이 {len(attempts)}번 시도 뒤에도 실패했어요.",
                "보내지 못한 사용자는 sent_at이 비어 있어 다음 알림 시각이나 재시작 때 다시 보내요."])
        return self.state["last_send"]

    async def verify_now(self, day: date) -> dict:
        """W1-a 검증. 실패도 상태로 남긴다 (미완료 요청은 verify_requests에 남아 다음 날 다시 꺼내진다)."""
        started = self.now()
        try:
            result = await self.verify(day)
            summary = {"status": "done", "date": str(day), "requests": len(result["items"]), "counts": result["counts"],
                       "trace_url": tracing.trace_url(result["trace_id"]) if result.get("trace_id") else None}
        except Exception as exc:
            log.exception("검증(W1-a) 실패")
            summary = {"status": "error", "date": str(day), "error": type(exc).__name__}
        self.state["last_verify"] = summary | {"started_at": started.isoformat(), "finished_at": self.now().isoformat()}
        return self.state["last_verify"]

    async def _alert(self, day: date, kind: str, title: str, lines: list[str]) -> None:
        sent = self.state["alerts"].setdefault(day, {})
        if kind in sent:
            return
        sent[kind] = await asyncio.to_thread(self.alert, title, lines)
        log.warning("실패 알림 %s: %s", sent[kind], title)

    async def _daily_run(self, today: date) -> None:
        """07:00 하루 실행과 재실행. 브리핑 없는 대상 사용자만 돌린다. 끝나면 run_checked, 남으면 30분 뒤 다시."""
        attempts = self.state["run_attempts"].get(today, 0)
        error = None
        try:
            missing = await self.missing_users(today)
            if missing:
                result = await self.run_now(user_ids=missing)
                if result.get("status") == "running":  # "지금 만들기"가 돌고 있으면 끝난 뒤 다시 본다
                    self.state["run_retry_at"] = self.now() + timedelta(seconds=MAX_NAP_SECONDS)
                    return
                attempts += 1
                error = (result.get("error") or "").split(":")[0] or None
                missing = await self.missing_users(today)
                # 실행이 늦게 끝나 이미 지나간 발송 시각이 있으면 다음 시각을 기다리지 않고 바로 보낸다 (10/1: 재시도가 10시에
                # 끝났는데 08·09시 발송은 빈 채로 지나가 12:00에야 나갔다). 발송은 sent_at 없는 사용자만이라 다시 불러도 안전하다
                done = self.state["sent_slots"].get(today, set())
                if any(slot in done for slot in SEND_SLOTS):
                    self.state["late_send"] = today
        except Exception as exc:  # DB 연결 실패 등. 예약 루프가 1분마다 같은 오류를 내지 않게 재시도 간격을 둔다
            log.exception("하루 실행 확인 실패")
            attempts, error, missing = attempts + 1, type(exc).__name__, None
        self.state["run_attempts"][today] = attempts
        if missing == []:
            self.state["run_checked"], self.state["run_retry_at"] = today, None
            return
        if attempts <= RUN_RETRIES:
            self.state["run_retry_at"] = self.now() + timedelta(seconds=RUN_RETRY_WAIT_SECONDS)
            log.warning("하루 실행 미완료(%s), %d분 뒤 다시 (%d/%d)", error or f"브리핑 없는 사용자 {len(missing or [])}명",
                        RUN_RETRY_WAIT_SECONDS // 60, attempts, RUN_RETRIES)
            return
        self.state["run_checked"], self.state["run_retry_at"] = today, None
        await self._alert(today, "run", f"{today:%m월 %d일} 하루 실행 실패", [
            f"하루 실행을 {attempts}번 시도했지만 끝내지 못했어요.",
            f"브리핑이 없는 대상 사용자: {len(missing)}명" if missing is not None else "대상 사용자를 확인하지 못했어요 (DB 연결 등).",
            f"마지막 오류 종류: {error}" if error else "마지막 실행은 끝났지만 모델 장애 등으로 빠진 사용자가 있어요.",
            "오늘은 더 시도하지 않아요. 브리핑이 있는 사용자는 알림 시각에 그대로 발송되고, 내일 07:00 예약은 그대로 돌아요."])

    async def tick(self) -> None:
        """지금 시각에 할 일을 한다. 루프가 매번 부른다."""
        now = self.now()
        today = now.date()
        if (VERIFY_AT <= now.time() < CATCH_UP_UNTIL and self.state["verify_done"] != today
                and (now.time() < RUN_AT or self.state["run_checked"] == today)):  # 늦게 켜지면 하루 실행 뒤로 미룬다
            self.state["verify_done"] = today
            self._verify_task = asyncio.create_task(self.verify_now(today))
        if WARM_AT <= now.time() < RUN_AT and self.state["warm_done"] != today:
            self.state["last_warm"] = {"results": await asyncio.to_thread(self.warm), "db": await self._wake_db(),
                                       "at": self.now().isoformat()}
            self.state["warm_done"] = today
        if today.weekday() == 0 and WARM_AT <= now.time() < CATCH_UP_UNTIL and self.state["merge_done"] != today:
            await self._merge(today)
        retry_at = self.state["run_retry_at"]
        if RUN_AT <= now.time() < CATCH_UP_UNTIL and self.state["run_checked"] != today and (retry_at is None or now >= retry_at):
            await self._daily_run(today)
        done = self.state["sent_slots"].setdefault(today, set())
        for slot in SEND_SLOTS:
            if slot <= now.time() < CATCH_UP_UNTIL and slot not in done:
                await self.send_now(today, slot.strftime("%H:%M"))
                done.add(slot)
        if self.state.get("late_send") == today:
            self.state["late_send"] = None
            await self.send_now(today, max(s for s in SEND_SLOTS if s in done).strftime("%H:%M"))

    async def _merge(self, today: date) -> None:
        try:
            result = await asyncio.to_thread(self.merge, today)
            self.state["last_merge"] = {"date": str(today), "reverted": len(result["reverted"]), "topics": result["topics"],
                                        "at": self.now().isoformat()}
        except Exception as exc:  # 합치기 실패는 브리핑을 막지 않는다. 다음 월요일에 다시 돈다
            log.exception("주간 기억 합치기 실패")
            self.state["last_merge"] = {"date": str(today), "error": type(exc).__name__, "at": self.now().isoformat()}
        self.state["merge_done"] = today

    async def _wake_db(self) -> str:
        try:
            await asyncio.to_thread(self.wake_db)
            return "ok"
        except Exception as exc:  # 깨우기 실패는 07:00 실행의 재시도·알림이 이어받는다
            log.warning("DB 깨우기 실패(%s)", type(exc).__name__)
            return type(exc).__name__

    def next_event(self) -> datetime:
        now = self.now()
        today = now.date()
        candidates = []
        if self.state["verify_done"] != today:
            candidates.append(datetime.combine(today, VERIFY_AT, now.tzinfo))
        if self.state["warm_done"] != today:
            candidates.append(datetime.combine(today, WARM_AT, now.tzinfo))
        if self.state["run_checked"] != today:
            candidates.append(self.state["run_retry_at"] or datetime.combine(today, RUN_AT, now.tzinfo))
        done = self.state["sent_slots"].get(today, set())
        candidates += [datetime.combine(today, slot, now.tzinfo) for slot in SEND_SLOTS if slot not in done]
        candidates = [c for c in candidates if c > now] or [datetime.combine(today + timedelta(days=1), VERIFY_AT, now.tzinfo)]
        return min(candidates)

    async def loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # 예약 루프는 죽지 않는다
                log.exception("예약 작업 실패")
            busy = self.running() or self.state["run_retry_at"] is not None or not (self._verify_task is None or self._verify_task.done())
            if self._restart is not None:  # 꺼지는 신호가 안 먹어도 예약은 계속 돈다
                self._restart.check(self.now(), busy, self.next_event())
            wait = (self.next_event() - self.now()).total_seconds()
            await self.sleep(max(1.0, min(wait, MAX_NAP_SECONDS)))

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._restart = autorestart.AutoRestart()
            self._task = asyncio.create_task(self.loop())
            log.warning("예약 작업 시작: 매일 %s 검증, %s 예열, %s 하루 실행, %s 발송 (KST)", VERIFY_AT.strftime("%H:%M"),
                        WARM_AT.strftime("%H:%M"), RUN_AT.strftime("%H:%M"), "·".join(NOTIFY_TIMES))

    async def stop(self) -> None:
        for task in (self._task, self._verify_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def status(self) -> dict:
        return {"enabled": self._task is not None and not self._task.done(), "running": self.running(),
                "next_event": self.next_event().isoformat(), **{k: self.state[k] for k in ("last_verify", "last_warm", "last_merge", "last_run", "last_send")},
                "run_retry_at": self.state["run_retry_at"].isoformat() if self.state["run_retry_at"] else None,
                "alerts": {str(day): kinds for day, kinds in self.state["alerts"].items()}}


scheduler = Scheduler()
