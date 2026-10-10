"""Railway 크론(pipeline/cron.py)과 웹 외부 작업 모드(JOBS_EXTERNAL=1) 검수 (2026-10-07). 가짜 시계·가짜 실행·발송·검증으로
확인한다. 모델·네트워크·메일·DB를 쓰지 않는다.

실행: uv run python -m tests.pipeline.check_cron
- 05:30·22:00 차례는 아무것도 안 함 / 06:00 차례는 DB 깨우기·검증(월요일이면 합치기)만, 실행·발송 안 함
- 07:00 차례: 브리핑 없는 사용자만 실행, 발송 시각 전이라 발송 안 함 / 07:30 차례: 남은 사용자 없으면 실행 안 함
- 08:00 차례: 먼저 08:00 발송(재시도·알림 있는 경로), 남은 사용자 재시도, 그래도 남으면 실패 알림 한 번
- 08:30 차례: 08:00 발송은 한 번만(재시도·알림 없음), 하루 실행은 안 함
- "지금 만들기" 요청: 그 사용자만 실행하고 요청을 지우고 발송을 다시 봄
- 같은 차례 정기 실행 대상의 요청은 두 번 만들지 않고 요청만 지움 (실패한 사용자는 요청을 남겨 다음 차례가 이어받음)
- 크론은 MCP_URL=inproc이 기본 / --rehearse는 관리자만 실행·발송한 뒤 그 날짜를 정리(실패해도 정리)
- 웹 JOBS_EXTERNAL=1: 지금 만들기는 요청만 남기고 상태는 DB로, /api/w1 실행·발송은 409
"""
import asyncio
import json
import os
import sys
from datetime import date, datetime
from types import SimpleNamespace

from fastapi import HTTPException

from pipeline import cron, persist, run_daily
from pipeline import scheduler as jobs
from pipeline.run_daily import KST

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


class World:
    """가짜 실행·발송·검증. missing은 브리핑 없는 사용자, still_missing은 실행 뒤에도 남는 사용자."""

    def __init__(self, at: str, missing=(), still_missing=(), requested=(), weekday_date=date(2026, 10, 7)):
        self.calls: list[tuple] = []
        self.missing, self.still_missing, self.requested = list(missing), list(still_missing), set(requested)
        self.ran = False
        hour, minute = map(int, at.split(":"))
        self.now = datetime(weekday_date.year, weekday_date.month, weekday_date.day, hour, minute, 5, tzinfo=KST)

    def scheduler(self) -> jobs.Scheduler:
        async def run(users=None, limit=None, user_ids=None):
            self.calls.append(("run", tuple(user_ids or ())))
            self.ran = True
            return {"date": str(self.now.date()), "totals": {}, "all_users_failed": False}

        def send(day, until):
            self.calls.append(("send", until))
            return {"mode": "smtp", "messages": 1, "sent": [1], "failed": []}

        async def verify(day):
            self.calls.append(("verify",))
            return {"items": [], "counts": {}, "trace_id": None}

        async def missing_users(day):
            return list(self.still_missing) if self.ran else list(self.missing)

        async def no_sleep(_seconds):
            return None
        return jobs.Scheduler(run=run, send=send, verify=verify, warm=lambda: [], wake_db=lambda: self.calls.append(("wake",)),
                              merge=lambda day: self.calls.append(("merge",)) or {"reverted": [], "topics": {}},
                              missing_users=missing_users, alert=lambda title, lines: self.calls.append(("alert", title)) or "sent",
                              now=lambda: self.now, sleep=no_sleep)


async def tick(world: World) -> dict:
    saved = (persist.requested_user_ids, persist.clear_requests)
    persist.requested_user_ids = lambda: set(world.requested)
    persist.clear_requests = lambda ids: world.calls.append(("clear", tuple(ids)))
    try:
        return await cron.tick(world.scheduler())
    finally:
        persist.requested_user_ids, persist.clear_requests = saved


def kinds(world: World) -> list:
    return [c[0] for c in world.calls]


async def cron_checks() -> None:
    for at in ("05:30", "22:00"):
        w = World(at, missing=[1])
        await tick(w)
        check(f"{at} 차례는 아무것도 안 함", w.calls == [])

    w = World("06:00", missing=[1])
    report = await tick(w)
    check("06:00 차례는 DB 깨우기·검증만", kinds(w) == ["wake", "verify"] and report["did"] == ["verify"])
    w = World("06:00", weekday_date=date(2026, 10, 5))  # 월요일
    await tick(w)
    check("월요일 06:00 차례는 합치기도", kinds(w) == ["wake", "verify", "merge"])

    w = World("07:00", missing=[1, 2])
    await tick(w)
    check("07:00 차례: 브리핑 없는 사용자만 실행, 발송 전이라 발송 없음", w.calls == [("run", (1, 2))])
    w = World("07:30")
    await tick(w)
    check("07:30 차례: 남은 사용자 없으면 실행 안 함", w.calls == [])

    w = World("08:00", missing=[2], still_missing=[2])
    await tick(w)
    check("08:00 차례: 발송 먼저, 남은 사용자 재시도, 그래도 남으면 실패 알림 한 번",
          w.calls[0] == ("send", "08:00") and ("run", (2,)) in w.calls and [c for c in w.calls if c[0] == "alert"] == [("alert", "10월 07일 하루 실행 실패")]
          and w.calls.index(("send", "08:00")) < w.calls.index(("run", (2,))))
    w = World("07:30", missing=[2], still_missing=[2])
    await tick(w)
    check("08:00 전 차례는 남아도 알림 없음", "alert" not in kinds(w))

    w = World("08:30", missing=[2])
    await tick(w)
    check("08:30 차례: 08:00 발송은 한 번만, 하루 실행 안 함", w.calls == [("send", "08:00")])
    w = World("12:00")
    await tick(w)
    check("12:00 차례: 08·09시는 한 번씩, 12시는 첫 차례 경로", w.calls == [("send", "08:00"), ("send", "09:00"), ("send", "12:00")])

    w = World("14:00", requested=[7])
    report = await tick(w)
    check("지금 만들기 요청: 그 사용자만 실행하고 요청을 지우고 발송을 다시 봄",
          ("run", (7,)) in w.calls and ("clear", (7,)) in w.calls and report["did"] == ["requested"] and "send_after" in report)
    w = World("06:30", requested=[7])
    await tick(w)
    check("07:00 전 요청은 07:00 차례에", w.calls == [])

    # 같은 사람 두 번 만들기 막기 (10/10 07:01: 정기 실행 4명 + 요청 1명이 따로 돌아 그 사람 것을 두 번 만들었다)
    w = World("07:00", missing=[1, 2, 3, 4], requested=[3])
    report = await tick(w)
    runs = [c for c in w.calls if c[0] == "run"]
    check("정기 실행 대상의 요청은 따로 만들지 않고 요청만 지움", runs == [("run", (1, 2, 3, 4))] and ("clear", (3,)) in w.calls
          and report["requested_skipped"] == {"done": [3], "kept": []} and "requested" not in report["did"])
    w = World("07:00", missing=[1, 2], requested=[2, 9])
    await tick(w)
    check("대상 밖 요청자(9)만 따로 실행하고, 대상 안(2)은 지우기만",
          [c for c in w.calls if c[0] == "run"] == [("run", (1, 2)), ("run", (9,))] and ("clear", (2,)) in w.calls and ("clear", (9,)) in w.calls)
    w = World("07:30", missing=[2, 3], still_missing=[3], requested=[2, 3])
    report = await tick(w)
    check("정기 실행이 실패한 사용자(3)는 요청을 남기고 성공한 사용자(2)만 지움, 다시 만들지 않음",
          [c for c in w.calls if c[0] == "run"] == [("run", (2, 3))] and [c for c in w.calls if c[0] == "clear"] == [("clear", (2,))]
          and report["requested_skipped"] == {"done": [2], "kept": [3]})
    w = World("08:30", missing=[3], requested=[3])
    await tick(w)
    check("정기 재시도가 끝난 차례(08:30)에는 남은 요청이 요청 처리로 이어받음", ("run", (3,)) in w.calls and ("clear", (3,)) in w.calls)

    failing = World("08:00")
    s = failing.scheduler()
    s.send = lambda day, until: failing.calls.append(("send", until)) or {"mode": "smtp", "messages": 1, "sent": [], "failed": [{"user_id": 1}]}
    saved = (persist.requested_user_ids, persist.clear_requests)
    persist.requested_user_ids, persist.clear_requests = (lambda: set()), (lambda ids: None)
    try:
        await cron.tick(s)
    finally:
        persist.requested_user_ids, persist.clear_requests = saved
    check("첫 차례 발송 실패는 10분 간격 2번 더 + 알림", [c for c in failing.calls if c[0] == "send"] == [("send", "08:00")] * 3
          and any(c[0] == "alert" for c in failing.calls))


async def rehearse_checks() -> None:
    calls = []
    saved = (run_daily.target_user_ids, cron._admin_ids, run_daily.run, cron.deliver.send_day, persist.delete_day)
    run_daily.target_user_ids = lambda: [45, 113]
    cron._admin_ids = lambda: {45}

    async def boom(day, **kw):
        calls.append(("run", day, tuple(kw["user_ids"])))
        raise RuntimeError("실행 실패")
    run_daily.run = boom
    persist.delete_day = lambda day, ids, since: calls.append(("cleanup", day, tuple(ids))) or {}
    try:
        try:
            await cron.rehearse(date(2000, 1, 8))
            raised = False
        except RuntimeError:
            raised = True
    finally:
        run_daily.target_user_ids, cron._admin_ids, run_daily.run, cron.deliver.send_day, persist.delete_day = saved
    check("--rehearse: 관리자만 실행하고 실패해도 그 날짜를 정리", raised and calls == [("run", date(2000, 1, 8), (45,)),
                                                                  ("cleanup", date(2000, 1, 8), (45,))])


def web_checks() -> None:
    from routes import settings, w1
    saved_env = {k: os.environ.get(k) for k in ("JOBS_EXTERNAL", "MCP_URL")}
    calls = []
    saved = (persist.request_briefing, persist.sent_user_ids, persist.requested_user_ids, persist.users_with_briefings)
    persist.request_briefing = lambda uid: calls.append(("request", uid))
    persist.sent_user_ids = lambda day: set()
    persist.requested_user_ids = lambda: {5}
    persist.users_with_briefings = lambda day: set()
    user = SimpleNamespace(id=5, role="개발자", is_test=True)
    try:
        os.environ["JOBS_EXTERNAL"] = "1"
        answer = asyncio.run(settings.make_now(user))
        status = settings.make_now_status(user)
        blocked = []
        for call in (lambda: w1.start_run(), lambda: w1.send(None)):
            try:
                asyncio.run(call())
            except HTTPException as exc:
                blocked.append(exc.status_code)
    finally:
        persist.request_briefing, persist.sent_user_ids, persist.requested_user_ids, persist.users_with_briefings = saved
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("외부 작업 모드: 지금 만들기는 요청만 남기고 202 응답", calls == [("request", 5)] and answer["started"] is True and "30분" in answer["message"])
    check("외부 작업 모드: 진행 상태는 DB 요청으로 running", status == {"status": "running"})
    check("외부 작업 모드: /api/w1 실행·발송은 409", blocked == [409, 409])
    check("기본(JOBS_EXTERNAL 없음)은 앱 안 예약 그대로", not jobs.external())


def inproc_default() -> None:
    saved = os.environ.pop("MCP_URL", None)
    original = asyncio.run
    try:
        cron.asyncio.run = lambda coro: coro.close() or {"at": "x", "did": []}
        cron.main([])
        value = os.environ.get("MCP_URL")
    finally:
        cron.asyncio.run = original
        if saved is None:
            os.environ.pop("MCP_URL", None)
        else:
            os.environ["MCP_URL"] = saved
    check("크론은 MCP_URL=inproc이 기본", value == "inproc")


asyncio.run(cron_checks())
asyncio.run(rehearse_checks())
web_checks()
inproc_default()
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
