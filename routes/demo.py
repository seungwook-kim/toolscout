"""공개 데모 /demo (2026-09-16 사용자 결정). 로그인 없이 데모 프로필의 최근 브리핑을 읽기 전용으로 보여 준다.

- GET /demo: 화면. 버튼·질문창·설정 링크 없음, 마스트헤드에 읽기 전용 안내와 로그인 링크. 검색엔진 색인 허용
- GET /api/demo/briefing: 데모 프로필(users.is_demo)의 가장 최근 브리핑. 파이프라인 숫자(큐레이터·검증관·해설가)는 그대로 보여 준다
- 실제 사용자 프로필·카드는 절대 나가지 않는다. 데모 프로필은 우리가 만든 가짜 하나뿐이다 (db.DEMO_USER)
- IP당 분당 60회. 넘으면 429 (프록시 뒤에서는 X-Forwarded-For 첫 주소를 본다)
데모 프로필은 하루 실행에 들어가 매일 갱신되고 메일은 받지 않는다 (가짜 주소라 deliver.outbox에서 뺀다).
"""
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

import db
from routes import briefings

router = APIRouter()
WEB = Path(__file__).resolve().parents[1] / "web"
RATE_WINDOW, RATE_LIMIT = 60.0, 60
NOTICE = "읽기 전용 데모입니다. 실제 서비스는 초대제로 운영합니다"
_hits: dict[str, list[float]] = defaultdict(list)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or (request.client.host if request.client else "?")


def rate_limit(request: Request) -> None:
    now = time.monotonic()
    ip = client_ip(request)
    recent = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(recent) >= RATE_LIMIT:
        _hits[ip] = recent
        raise HTTPException(status_code=429, detail="잠시 뒤에 다시 열어 주세요")
    _hits[ip] = recent + [now]


def demo_user() -> db.User | None:
    with db.session() as s:
        return s.exec(select(db.User).where(db.User.is_demo == True).order_by(db.User.id)).scalars().first()  # noqa: E712


def latest_day(user_id: int) -> date | None:
    with db.get_engine().connect() as conn:
        return conn.execute(select(func.max(db.Briefing.date)).where(db.Briefing.user_id == user_id)).scalar()


@router.get("/demo", include_in_schema=False)
def demo_page(request: Request) -> FileResponse:
    rate_limit(request)
    return FileResponse(WEB / "demo.html", headers={"Cache-Control": "no-store"})


@router.get("/api/demo/briefing")
def demo_briefing(request: Request) -> dict:
    rate_limit(request)
    user = demo_user()
    if user is None:
        return {"demo": True, "notice": NOTICE, "exists": False, "cards": [], "count": 0, "date": str(date.today()),
                "profile_line": "", "empty_reason": "데모 브리핑이 아직 없어요"}
    day = latest_day(user.id)
    if day is None:
        return {"demo": True, "notice": NOTICE, "exists": False, "cards": [], "count": 0, "date": str(date.today()),
                "profile_line": briefings.profile_line(user), "empty_reason": "데모 브리핑이 아직 없어요"}
    data = briefings.briefing_for(user, day)
    data.pop("is_admin", None)  # 트레이스 링크는 데모에 없다
    for card in data["cards"]:
        card.pop("trace_url", None)
        card["feedback"] = {"actions": [], "reason": None, "memo": None, "ids": {}}
    return {"demo": True, "notice": NOTICE, **data}
