"""아침 브리핑 작업(W1)을 사람이 직접 부르는 API. 평소에는 앱 안 예약(pipeline/scheduler.py)이 07:00·08:00에 돈다.

모두 X-Service-Key(MCP_SERVICE_KEY)로 검문한다.
- POST /api/w1/run?users=&limit=: 하루 실행을 백그라운드로 시작(202). 이미 돌고 있으면 409
- POST /api/w1/send?date=: 그날 미발송 메일을 지금 보낸다. 하루 실행이 돌고 있으면 끝날 때까지 기다린다
- GET  /api/w1/status: 예약 켜짐 여부, 실행 중 여부, 다음 예정 시각, 마지막 실행·발송 요약
"""
import asyncio
import hmac
import os
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from pipeline.scheduler import scheduler


def service_key(x_service_key: str = Header(default="")) -> None:
    expected = os.environ.get("MCP_SERVICE_KEY", "")
    if not expected or not hmac.compare_digest(x_service_key, expected):
        raise HTTPException(status_code=401, detail="서비스 키가 없거나 틀림")


router = APIRouter(prefix="/api/w1", dependencies=[Depends(service_key)])
_background: set[asyncio.Task] = set()


@router.post("/run", status_code=202)
async def start_run(users: int | None = None, limit: int | None = None) -> dict:
    if scheduler.running():
        raise HTTPException(status_code=409, detail="하루 실행이 이미 돌고 있다")
    task = asyncio.create_task(scheduler.run_now(users=users, limit=limit))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"started": True}


@router.post("/send")
async def send(day: date | None = Query(default=None, alias="date")) -> dict:
    return await scheduler.send_now(day)


@router.get("/status")
async def status() -> dict:
    return scheduler.status()
