"""공개 데모 /demo (2026-09-16 사용자 결정, 2026-10-08 고정 예시로 바꿈). 로그인 없이 읽기 전용으로 본다.

2026-10-08 사용자 결정 "회원가입을 원치 않는 사람은 데모버전을 눈으로 볼 수 있는 가짜 뉴스화면": DB·모델 없이 web/demo_sample.json의
고정 예시 카드(가상의 회사·제품, 제목에 [예시], 링크는 example.com)를 보여 준다. 실제 사용자 프로필·카드는 절대 나가지 않는다.
- GET /demo: 화면. 버튼·질문창·설정 링크 없음, 마스트헤드에 예시 안내와 로그인 링크. 검색엔진 색인 허용
- GET /api/demo/briefing: 고정 예시 브리핑 (오늘 화면과 같은 모양)
- IP당 분당 60회. 넘으면 429 (프록시 뒤에서는 X-Forwarded-For 첫 주소를 본다)
- 보호 2차 (2026-10-09): /api/demo/briefing은 DB 요청 수 제한(비로그인 분당 30, routes/guard.py)도 거치고, 카드 본문 글 끝에 "데모" 고정
  워터마크(routes/watermark.py)를 붙인다. 위 메모리 제한은 서버리스에서는 인스턴스마다 따로라 느슨한 보조 장치다
"""
import json
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from routes import guard, watermark

router = APIRouter()
WEB = Path(__file__).resolve().parents[1] / "web"
RATE_WINDOW, RATE_LIMIT = 60.0, 60
NOTICE = "가입 없이 보는 예시 화면이에요. 회사·제품·기사는 모두 가상의 예시예요"
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


def sample() -> dict:
    data = json.loads((WEB / "demo_sample.json").read_text(encoding="utf-8"))
    for card in data["cards"]:
        card["feedback"] = {"actions": [], "reason": None, "memo": None, "ids": {}}
    return data


@router.get("/demo", include_in_schema=False)
def demo_page(request: Request) -> FileResponse:
    rate_limit(request)
    return FileResponse(WEB / "demo.html", headers={"Cache-Control": "no-store"})


@router.get("/api/demo/briefing", dependencies=[Depends(guard.rate_limit)])
def demo_briefing(request: Request) -> dict:
    rate_limit(request)
    data = sample()
    data["cards"] = watermark.mark_cards(data["cards"], watermark.mark_for(watermark.DEMO))
    return {"demo": True, "notice": NOTICE, **data}
