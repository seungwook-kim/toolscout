"""프로필·설정 API (계획안 5장 기억 설계, 부록 C 「내 기억 지우기」, 6장 "가입 즉시 오늘 브리핑"). 모두 세션 필요.

- GET  /api/profile: 직군 목록·프리셋·주제 10개·내 프로필(가중치 없으면 프리셋)·첫 설정 여부
- POST /api/profile: 직군(필수)·주제 관심도(-5~+5)·쓰는 도구 태그·자유 한 줄·알림 채널·시간 저장, 가중치 초기값 반영
- POST /api/memory/forget: weights·seen·feedback 삭제 / POST /api/account/delete: 계정과 기록 전부 삭제, 세션 끝
- POST /api/briefing/now: 이 사용자만 오늘 브리핑을 지금 만든다(백그라운드) / GET /api/briefing/now: 진행 상태
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
import memory
import models
from agent.schemas import TOPICS
from pipeline import persist, run_daily
from pipeline.scheduler import scheduler
from routes.auth import SESSION_COOKIE, profile_done, require_user

router = APIRouter()
_runs: dict[int, dict] = {}  # 사용자별 "지금 만들기" 상태 (프로세스 메모리)
_tasks: set[asyncio.Task] = set()


class ProfileBody(BaseModel):
    role: str
    tools_tags: list[str] = Field(default_factory=list)
    free_text: str | None = None
    weights: dict[str, int] = Field(default_factory=dict)
    notify_time: str = "08:00"
    channel: str = "email"


@router.get("/api/profile")
def get_profile(user: db.User = Depends(require_user)) -> dict:
    return {"roles": memory.ROLE_CHOICES, "presets": memory.ROLE_PRESETS, "topics": TOPICS,
            "notify_times": memory.NOTIFY_TIMES, "channels": [{"id": "email", "label": "이메일", "ready": True},
                                                            {"id": "kakao", "label": "카카오톡 (준비 중)", "ready": False}],
            "profile": memory.profile(user.id), "first_time": not profile_done(user), "dev_mode": models.dev_mode()}


@router.post("/api/profile")
def save_profile(body: ProfileBody, user: db.User = Depends(require_user)) -> dict:
    try:
        memory.save_profile(user.id, role=body.role, tools_tags=body.tools_tags, free_text=body.free_text,
                            weights=body.weights, notify_time=body.notify_time, channel=body.channel)
    except memory.ProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True, "message": "저장했어요. 내일 브리핑부터 반영돼요"}


@router.post("/api/memory/forget")
def forget(user: db.User = Depends(require_user)) -> dict:
    counts = memory.forget(user.id)
    return {"ok": True, "deleted": counts, "message": "기억을 지웠어요. 다음 브리핑은 프로필만으로 골라요"}


@router.post("/api/account/delete")
def delete_account(user: db.User = Depends(require_user)) -> JSONResponse:
    memory.delete_account(user.id)
    response = JSONResponse({"ok": True, "message": "계정과 기록을 모두 지웠어요"})
    response.delete_cookie(SESSION_COOKIE)
    return response


async def _make_now(user_id: int) -> None:
    result = await scheduler.run_now(user_ids=[user_id])
    _runs[user_id] = {"status": "done" if result.get("status") == "done" else "error",
                      "result": {k: result.get(k) for k in ("status", "date", "totals", "error")}}


@router.post("/api/briefing/now", status_code=202)
async def make_now(user: db.User = Depends(require_user)) -> dict:
    if not profile_done(user):
        raise HTTPException(status_code=400, detail="프로필을 먼저 저장해 주세요")
    if models.dev_mode() and not user.is_test:
        raise HTTPException(status_code=403, detail="개발 모드에서는 브리핑 대상 사용자만 만들 수 있어요")
    today = run_daily.today_kst()
    if user.id in await asyncio.to_thread(persist.sent_user_ids, today):
        raise HTTPException(status_code=409, detail="오늘 브리핑은 이미 보냈어요")
    if scheduler.running():
        raise HTTPException(status_code=409, detail="지금 다른 브리핑을 만드는 중이에요. 잠시 뒤 다시 눌러 주세요")
    _runs[user.id] = {"status": "running"}
    task = asyncio.create_task(_make_now(user.id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"started": True, "message": "오늘 브리핑을 만드는 중이에요. 10분쯤 걸려요"}


@router.get("/api/briefing/now")
def make_now_status(user: db.User = Depends(require_user)) -> dict:
    return _runs.get(user.id, {"status": "idle"})
