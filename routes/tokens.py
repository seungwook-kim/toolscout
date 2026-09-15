"""서명 토큰 (로그인 링크·세션·피드백 링크). SESSION_SECRET로 HMAC-SHA256 서명한다. 새 라이브러리 없이 표준 라이브러리만.

토큰 모양: base64url(JSON 내용).base64url(서명). 내용에 목적(purpose)·만료(exp)·임의값(n)이 들어간다.
- verify: 서명·목적·만료 확인. 틀리면 TokenError("invalid"), 만료면 TokenError("expired")
- consume: 1회용 토큰을 쓴다. used_tokens에 해시를 넣고, 이미 있으면 TokenError("used")
토큰 원문과 SESSION_SECRET 값은 로그·응답에 쓰지 않는다 (작업 규칙 8·11).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert

import config  # noqa: F401  .env를 os.environ에 채운다
import db


class TokenError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # invalid / expired / used


def _secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET", "")
    if len(secret) < 16:
        raise RuntimeError("SESSION_SECRET이 비었거나 너무 짧다 (16자 이상)")
    return secret.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(purpose: str, data: dict, ttl_seconds: int) -> str:
    body = _b64(json.dumps({**data, "p": purpose, "exp": int(time.time()) + ttl_seconds, "n": secrets.token_hex(8)},
                           separators=(",", ":"), ensure_ascii=False).encode())
    mac = hmac.new(_secret(), f"{purpose}.{body}".encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def verify(token: str, purpose: str) -> dict:
    try:
        body, mac = token.split(".", 1)
        expected = hmac.new(_secret(), f"{purpose}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_unb64(mac), expected):
            raise TokenError("invalid")
        data = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("invalid") from exc
    if data.get("p") != purpose:
        raise TokenError("invalid")
    if data.get("exp", 0) < time.time():
        raise TokenError("expired")
    return data


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def consume(token: str, purpose: str) -> dict:
    """1회용 토큰을 확인하고 쓴 것으로 표시한다. 두 번째부터는 TokenError("used")."""
    data = verify(token, purpose)
    statement = (insert(db.UsedToken).values(
        token_hash=token_hash(token), purpose=purpose, used_at=datetime.now(timezone.utc),
        expires_at=datetime.fromtimestamp(data["exp"], timezone.utc))
        .on_conflict_do_nothing(index_elements=["token_hash"]).returning(db.UsedToken.token_hash))
    with db.get_engine().begin() as connection:
        # rowcount는 드라이버에 따라 믿을 수 없어서(실측: 이미 있는 토큰도 통과) 실제로 들어간 행을 돌려받아 확인한다
        if connection.execute(statement).first() is None:
            raise TokenError("used")
    return data
