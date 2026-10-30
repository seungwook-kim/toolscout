"""Railway 크론 진입점 (2026-10-07 사용자 결정 "vercel + railway": 정해진 시각에 켜져서 할 일을 하고 끝난다).

실행: python -m pipeline.cron  (railway.json cronSchedule: KST 06:00~21:30, 30분마다)
     python -m pipeline.cron --rehearse 2000-01-08  (서버 첫 점검: 검수용 날짜로 관리자만 실행 → 그 날짜 메일 발송 → 정리)
매번 새 프로세스라 앱 안 예약(pipeline/scheduler.py)처럼 상태를 메모리에 둘 수 없다. 지금 시각과 DB만 보고 할 일을 한다.
같은 Scheduler의 실행·발송·검증·알림 함수를 그대로 쓴다.
- 06:00 차례: DB 깨우기, 검증(W1-a), 월요일이면 주간 기억 합치기
- 07:00·07:30·08:00 차례: 브리핑 없는 대상 사용자만 하루 실행(첫 시도 + 재시도 2번, 앱 안 예약과 같은 횟수). 08:00 차례에도 남으면 실패 알림
- 07:00~21:59 모든 차례: "지금 만들기" 요청 사용자(users.briefing_requested_at)만 실행하고 요청을 지운다.
  같은 차례 정기 실행 대상에 든 사용자는 따로 만들지 않는다(성공했으면 요청만 지우고, 실패했으면 요청을 남겨 다음 차례가 이어받음)
- 07:00~21:59 모든 차례: 지난 알림 시각(08·09·12·18시)의 미발송 메일을 보낸다(sent_at 기준 멱등). 실행 앞뒤로 두 번 본다.
  알림 시각 뒤 첫 차례는 실패 재시도(10분 간격 2번)와 실패 알림까지, 그 뒤 차례는 한 번만 보낸다(같은 알림이 반복되지 않게)
- 도구(MCP)는 같은 프로세스의 mcp_server에 메모리로 붙는다(MCP_URL=inproc, agent/loop.py). 서버를 띄우지 않는다
- 이전 차례가 아직 돌고 있으면 Railway가 이번 차례를 건너뛴다
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

import config  # noqa: F401  .env를 os.environ에 채운다 (Railway에서는 서비스 변수)
import embeddings
from agent import tracing
from pipeline import deliver, persist, run_daily
from pipeline import scheduler as jobs

log = logging.getLogger("toolscout.cron")

SLOT_MINUTES = 30  # railway.json cronSchedule 간격
VERIFY_UNTIL = time(6, 30)  # 06:00 차례만 검증
RUN_UNTIL, RUN_LAST_TRY = time(8, 30), time(8, 0)  # 07:00·07:30·08:00 차례가 하루 실행 (마지막 차례 뒤 실패 알림)


async def _send_due(s: jobs.Scheduler, now: datetime) -> list[dict]:
    out = []
    for slot in jobs.SEND_SLOTS:
        if slot > now.time():
            continue
        until = slot.strftime("%H:%M")
        if datetime.combine(now.date(), slot, now.tzinfo) > now - timedelta(minutes=SLOT_MINUTES):  # 알림 시각 뒤 첫 차례
            result = await s.send_now(now.date(), until)
            out.append({"until": until, "attempts": len(result["attempts"]), "failed": len(result["failed"])})
        else:
            result = await asyncio.to_thread(s.send, now.date(), until)
            if result["messages"]:
                out.append({"until": until, "attempts": 1, "sent": len(result["sent"]), "failed": len(result["failed"])})
    return out


async def tick(s: jobs.Scheduler | None = None) -> dict:
    """지금 시각에 할 일을 한다. 반환: 한 일 요약."""
    s = s or jobs.Scheduler()
    now = s.now()
    today, t = now.date(), now.time()
    report: dict = {"at": now.isoformat(timespec="minutes"), "did": []}
    if t < jobs.VERIFY_AT or t >= jobs.CATCH_UP_UNTIL:
        return report
    if t < VERIFY_UNTIL:
        report["db"] = await s._wake_db()
        report["verify"] = await s.verify_now(today)
        report["did"].append("verify")
        if today.weekday() == 0:
            await s._merge(today)
            report["merge"] = s.state["last_merge"]
    if t < jobs.RUN_AT:
        return report
    report["send_before"] = await _send_due(s, now)
    ran_ids: set[int] = set()  # 이 차례의 정기 실행 대상. 같은 차례의 "지금 만들기"가 같은 사람을 또 만들지 않게 한다
    if t < RUN_UNTIL:
        missing = await s.missing_users(today)
        if missing:
            ran_ids = set(missing)
            report["run"] = await s.run_now(user_ids=missing)
            report["did"].append("run")
            missing = await s.missing_users(today)
        if missing and t >= RUN_LAST_TRY:
            await s._alert(today, "run", f"{today:%m월 %d일} 하루 실행 실패", [
                f"07:00·07:30·08:00 세 번 시도했지만 브리핑이 없는 대상 사용자 {len(missing)}명이 남았어요.",
                "오늘은 더 시도하지 않아요. 브리핑이 있는 사용자는 알림 시각에 그대로 발송되고, 내일 07:00 크론은 그대로 돌아요."])
    requested = sorted(await asyncio.to_thread(persist.requested_user_ids))
    if requested and ran_ids:
        # 10/10 07:01에 정기 실행(4명)과 요청 처리(1명)가 같은 차례에 따로 돌아 그 사람 것을 두 번 만들었다(모델 호출 33번 추가).
        # 정기 실행 대상에 든 사용자의 요청은 따로 만들지 않는다. 정기 실행이 만든 사람은 요청만 지우고, 실패한 사람은 요청을 남겨
        # 다음 차례(정기 재시도가 끝난 뒤에는 요청 처리)가 이어받는다
        failed_ids = set(await s.missing_users(today))
        covered = [uid for uid in requested if uid in ran_ids]
        done = [uid for uid in covered if uid not in failed_ids]
        if done:
            await asyncio.to_thread(persist.clear_requests, done)
        report["requested_skipped"] = {"done": done, "kept": [uid for uid in covered if uid in failed_ids]}
        requested = [uid for uid in requested if uid not in ran_ids]
    if requested:
        report["requested"] = await s.run_now(user_ids=requested)
        await asyncio.to_thread(persist.clear_requests, requested)  # 실패해도 지운다. 사용자가 다시 누를 수 있다
        report["did"].append("requested")
    if "run" in report["did"] or "requested" in report["did"]:
        report["send_after"] = await _send_due(s, s.now())
    report["embed"] = await asyncio.to_thread(embeddings.embed_missing)  # 새 항목 벡터(키·표가 없으면 0, 실패해도 크론은 계속)
    return report


async def rehearse(day: date) -> dict:
    """서버 첫 점검: 검수용 날짜로 관리자 계정만 실제 수집·모델·도구로 실행 → 그 날짜 메일 발송 → 그 날짜 브리핑·이번 seen 정리."""
    started = datetime.now(timezone.utc)
    targets, admin_ids = await asyncio.to_thread(run_daily.target_user_ids), await asyncio.to_thread(_admin_ids)
    admins = [uid for uid in targets if uid in admin_ids]
    try:
        run = await run_daily.run(day, user_ids=admins, limit=40)
        send = await asyncio.to_thread(deliver.send_day, day)
    finally:
        cleanup = await asyncio.to_thread(persist.delete_day, day, admins, started)
    return {"date": str(day), "users": admins, "totals": run["totals"], "providers": run.get("providers"),
            "failovers": run.get("failovers"), "seconds": run.get("seconds"), "trace_url": run.get("trace_url"),
            "send": {k: send.get(k) for k in ("mode", "messages", "sent", "failed")}, "cleanup": cleanup}


def _admin_ids() -> set[int]:
    from sqlmodel import select

    import db
    with db.session() as session:
        return set(session.exec(select(db.User.id).where(db.User.is_admin == True)))  # noqa: E712


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="toolscout Railway 크론 (지금 시각에 할 일만 하고 끝난다)")
    parser.add_argument("--rehearse", type=date.fromisoformat, default=None, help="서버 첫 점검용 검수 날짜 (예: 2000-01-08)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    os.environ.setdefault("MCP_URL", "inproc")  # 크론은 MCP 서버를 띄우지 않는다
    try:
        report = asyncio.run(rehearse(args.rehearse) if args.rehearse else tick())
    finally:
        tracing.flush()
    print(json.dumps(report, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
