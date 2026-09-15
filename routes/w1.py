"""n8n W1이 부르는 API (계획안 9.2 W1). 모두 X-Service-Key(MCP_SERVICE_KEY)로 검문한다.

- POST /api/w1/run: 하루 실행(수집 → 저장)을 백그라운드로 시작. 이미 돌고 있으면 409
- GET  /api/w1/status: 실행 중 여부와 마지막 실행 요약 (날짜·합계·종료 코드·트레이스 주소)
- GET  /api/w1/outbox?date=: 그날 미발송 사용자별 메일 (제목·HTML·텍스트). dev_mode면 n8n은 보내지 않는다
- POST /api/w1/sent: 보낸 사용자의 sent_at 기록 (멱등)
"""
import asyncio
import hmac
import logging
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

import models
from pipeline import deliver, run_daily

log = logging.getLogger("toolscout.w1")

_state: dict = {"task": None, "last": None}


def service_key(x_service_key: str = Header(default="")) -> None:
    expected = os.environ.get("MCP_SERVICE_KEY", "")
    if not expected or not hmac.compare_digest(x_service_key, expected):
        raise HTTPException(status_code=401, detail="서비스 키가 없거나 틀림")


router = APIRouter(prefix="/api/w1", dependencies=[Depends(service_key)])


class SentRequest(BaseModel):
    date: date
    user_ids: list[int]


async def _run(users: int | None, limit: int | None) -> None:
    started = datetime.now(timezone.utc)
    try:
        report = await run_daily.run(users=users, limit=limit)
        _state["last"] = {"date": report["date"], "totals": report["totals"], "exit_code": run_daily.exit_code(report),
                          "trace_url": report["trace_url"], "source_failures": report["source_failures"],
                          "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:  # 실행 실패도 상태로 남겨 n8n이 알림을 보낼 수 있게 한다
        log.exception("하루 실행 실패")
        _state["last"] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}", "exit_code": 1,
                          "started_at": started.isoformat(), "finished_at": datetime.now(timezone.utc).isoformat()}


@router.post("/run", status_code=202)
async def start_run(users: int | None = None, limit: int | None = None) -> dict:
    task = _state["task"]
    if task is not None and not task.done():
        raise HTTPException(status_code=409, detail="하루 실행이 이미 돌고 있다")
    _state["task"] = asyncio.create_task(_run(users, limit))
    return {"started": True, "date": str(run_daily.today_kst()), "dev_mode": models.dev_mode()}


@router.get("/status")
async def status() -> dict:
    task = _state["task"]
    return {"running": task is not None and not task.done(), "last": _state["last"]}


@router.get("/outbox")
async def get_outbox(day: date | None = Query(default=None, alias="date")) -> dict:
    day = day or run_daily.today_kst()
    messages = await asyncio.to_thread(deliver.outbox, day)
    if models.dev_mode():
        for message in messages:
            log.warning("[개발 모드 발송 안 함] %s · %s · 카드 %s장", message["to"], message["subject"], message["cards"])
    return {"date": str(day), "dev_mode": models.dev_mode(), "count": len(messages), "messages": messages}


@router.post("/sent")
async def post_sent(body: SentRequest) -> dict:
    rows = await asyncio.to_thread(deliver.mark_sent, body.user_ids, body.date)
    return {"date": str(body.date), "user_ids": body.user_ids, "rows_marked": rows}
