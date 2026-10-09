"""무단 긁어 가기 2차 보호: 함정 링크·24시간 차단·요청 수 제한 (2026-10-09 사용자 결정).

함정 링크
- 공개 화면과 앱 화면에 사람 눈에 안 보이고 키보드 포커스도 안 가는 링크(TRAP_PATH)가 하나 있다. robots.txt는 이 경로를 Disallow 한다.
  규칙을 읽지 않고 링크를 따라가는 봇만 이 경로를 부른다. 메일에는 넣지 않는다(메일 보안 검사기가 링크를 눌러 오탐이 난다)
- 부른 클라이언트(IP + User-Agent를 SESSION_SECRET로 HMAC한 값)를 blocked_clients에 24시간 차단으로 적는다. 원래 IP·UA는 저장하지 않는다.
  Vercel에서는 x-forwarded-for(첫 주소)·x-real-ip가 진짜 접속자 주소다
- 차단된 클라이언트의 요청은 robots.txt 말고 403 (routes/protect.py 미들웨어). 단 유효한 로그인 세션 쿠키가 있으면 막지 않고 함정도 기록하지 않는다
  (같은 회사 공유기 뒤의 진짜 사용자를 잠그지 않으려고). 이때는 경고 로그만 남긴다
요청 수 제한
- 브리핑·검색·지난 브리핑·데모 API에 고정 창(1분) 카운터를 DB 한 번(upsert)으로 센다. 로그인 사용자는 사용자별, 비로그인은 클라이언트 HMAC별.
  넘으면 429 + Retry-After. 로그인·가입은 자체 제한이 있어 그대로 둔다. DB가 느리거나 실패하면 막지 않고 통과(로그만)
- 기준(환경변수로 바꿈): 로그인 RATE_LIMIT_USER 분당 120, 비로그인 RATE_LIMIT_ANON 분당 30. RATE_LIMIT_OFF=1이면 끈다(검수용, 운영 기본은 켜짐)
못 막는 것: 로그인한 사용자가 느리게 천천히 긁는 것, IP·UA를 바꿔 가며 오는 봇, 규칙을 지키되 사람처럼 화면을 직접 받아 가는 사람.
x-forwarded-for는 Vercel 밖(직접 접속)에서는 접속자가 꾸밀 수 있다
"""
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

import db
from routes import tokens
from routes.auth import SESSION_COOKIE

log = logging.getLogger("toolscout.guard")
router = APIRouter(include_in_schema=False)

TRAP_PATH = "/archive/full-index"
BLOCK_HOURS = 24
DB_TIMEOUT_MS = 1500  # 이 시간보다 오래 걸리는 질의는 포기하고 통과시킨다
NEG_CACHE_SECONDS = 15  # "차단 아님" 확인 결과를 같은 서버 프로세스 안에서 잠깐 기억(요청마다 DB를 부르지 않으려고)
POS_CACHE_SECONDS = 60  # "차단 중"도 1분만 기억하고 DB를 다시 본다. 관리자가 차단 행을 지우면 1분 안에 풀린다 (2026-10-09 운영 확인: 끝날 때까지 기억하면 행을 지워도 따뜻한 서버에서 계속 403이었다)
DEFAULT_USER_LIMIT, DEFAULT_ANON_LIMIT, WINDOW_SECONDS = 120, 30, 60
LIMIT_MESSAGE = "요청이 너무 많아요. 잠시 뒤에 다시 열어 주세요"
BLOCK_MESSAGE = "접근이 제한됐어요. 24시간 뒤에 다시 시도해 주세요"

clock = time.time  # 검수가 시각을 바꿔 보려고 갈아 끼운다
_known: dict[str, tuple[float, datetime | None]] = {}  # client_hash -> (확인한 시각, 차단 만료 시각 또는 None)


def now() -> datetime:
    """지금(UTC, 시간대 표시 없이). DB 칸이 시간대 없는 시각이라 맞춰 쓴다."""
    return datetime.fromtimestamp(clock(), timezone.utc).replace(tzinfo=None)


def clear_cache() -> None:
    _known.clear()


# ---------- 누구인가 ----------
def client_ip(headers, peer: str | None) -> str:
    """headers: 소문자 이름으로 get 되는 것. 프록시(Vercel) 뒤에서는 x-forwarded-for 첫 주소, 없으면 x-real-ip."""
    forwarded = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return forwarded or (headers.get("x-real-ip") or "").strip() or peer or "?"


def client_hash(ip: str, user_agent: str) -> str:
    return tokens.derive("client", f"{ip}|{user_agent}").hex()[:32]


def client_of(headers, peer: str | None) -> str:
    return client_hash(client_ip(headers, peer), headers.get("user-agent") or "")


def session_uid(cookie_header: str | None) -> int | None:
    """쿠키 헤더에 서명·만료가 맞는 로그인 세션이 있으면 사용자 번호(DB를 부르지 않음)."""
    if not cookie_header:
        return None
    try:
        jar = SimpleCookie(cookie_header)
        morsel = jar.get(SESSION_COOKIE)
        return tokens.verify(morsel.value, "session").get("uid") if morsel else None
    except Exception:  # noqa: BLE001  깨진 쿠키는 세션 없음으로 본다
        return None


# ---------- DB 도우미 ----------
def _timed(conn) -> None:
    conn.exec_driver_sql(f"SET LOCAL statement_timeout = {DB_TIMEOUT_MS}")


def cleanup() -> None:
    """만료된 차단 기록과 한 시간 지난 카운터를 지운다(가끔 부른다)."""
    current = now()
    with db.get_engine().begin() as conn:
        _timed(conn)
        conn.execute(delete(db.BlockedClient).where(db.BlockedClient.expires_at < current))
        conn.execute(delete(db.RateCounter).where(db.RateCounter.window < int(clock() // WINDOW_SECONDS) - 60))


# ---------- 함정과 차단 ----------
def is_blocked(client: str) -> bool:
    """이 클라이언트가 지금 차단 중인가. DB가 안 되면 False(통과)."""
    current = now()
    seen = _known.get(client)
    if seen and seen[1] is not None and seen[1] > current and clock() - seen[0] < POS_CACHE_SECONDS:
        return True
    if seen and seen[1] is None and clock() - seen[0] < NEG_CACHE_SECONDS:
        return False
    try:
        with db.get_engine().connect() as conn:
            _timed(conn)
            expires = conn.execute(select(db.BlockedClient.expires_at).where(
                db.BlockedClient.client_hash == client, db.BlockedClient.expires_at > current)).scalar()
    except Exception as exc:  # noqa: BLE001  DB 문제로 진짜 사용자를 막지 않는다
        log.warning("차단 확인 실패, 통과시킴: %s", type(exc).__name__)
        _known[client] = (clock(), None)
        return False
    _known[client] = (clock(), expires)
    return expires is not None


def record_trap(client: str) -> bool:
    """함정을 부른 클라이언트를 24시간 차단으로 적는다(다시 부르면 시간을 새로 24시간으로). 반환: 기록 성공 여부."""
    current = now()
    expires = current + timedelta(hours=BLOCK_HOURS)
    try:
        statement = insert(db.BlockedClient).values(client_hash=client, path=TRAP_PATH, hits=1, blocked_at=current, expires_at=expires)
        statement = statement.on_conflict_do_update(index_elements=["client_hash"], set_={
            "hits": db.BlockedClient.hits + 1, "blocked_at": current, "expires_at": expires})
        with db.get_engine().begin() as conn:
            _timed(conn)
            conn.execute(statement)
        cleanup()
    except Exception as exc:  # noqa: BLE001
        log.warning("함정 기록 실패: %s", type(exc).__name__)
        return False
    _known[client] = (clock(), expires)
    return True


@router.get(TRAP_PATH)
def trap(request: Request) -> PlainTextResponse:
    uid = session_uid(request.headers.get("cookie"))
    client = client_of(request.headers, request.client.host if request.client else None)
    if uid:
        log.warning("로그인 세션이 함정 링크를 불렀음(차단 안 함): 사용자 %s", uid)
    else:
        record_trap(client)
    return PlainTextResponse(BLOCK_MESSAGE, status_code=403)


# ---------- 요청 수 제한 ----------
def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def count_hit(key: str) -> int:
    """이 창(1분)에서 key의 요청 수를 하나 올리고 올린 뒤 값을 돌려준다(upsert 한 번)."""
    window = int(clock() // WINDOW_SECONDS)
    statement = insert(db.RateCounter).values(key=key, window=window, count=1)
    statement = statement.on_conflict_do_update(index_elements=["key", "window"], set_={"count": db.RateCounter.count + 1})
    with db.get_engine().begin() as conn:
        _timed(conn)
        return conn.execute(statement.returning(db.RateCounter.count)).scalar_one()


def rate_limit(request: Request) -> None:
    """FastAPI 의존성. 기준을 넘으면 429(한국어 안내 + Retry-After). DB 문제면 통과."""
    if os.environ.get("RATE_LIMIT_OFF") == "1":
        return
    uid = session_uid(request.headers.get("cookie"))
    if uid:
        key, limit = f"u:{uid}", _limit("RATE_LIMIT_USER", DEFAULT_USER_LIMIT)
    else:
        key, limit = f"c:{client_of(request.headers, request.client.host if request.client else None)}", _limit("RATE_LIMIT_ANON", DEFAULT_ANON_LIMIT)
    try:
        used = count_hit(key)
        if random.random() < 0.01:
            cleanup()
    except Exception as exc:  # noqa: BLE001
        log.warning("요청 수 세기 실패, 통과시킴: %s", type(exc).__name__)
        return
    if used > limit:
        wait = max(1, WINDOW_SECONDS - int(clock() % WINDOW_SECONDS))
        raise HTTPException(status_code=429, detail=f"{LIMIT_MESSAGE} ({wait}초 뒤)", headers={"Retry-After": str(wait)})
