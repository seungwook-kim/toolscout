"""Gmail API(HTTPS)로 메일 보내기 (2026-10-09 사용자 결정 "Gmail API로 보내기").
Railway(Hobby)는 바깥 SMTP(25·465·587)를 막아서 smtplib로는 못 보낸다. 같은 Gmail 계정을 HTTPS(443)로 쓴다.

- 환경변수 MAIL_TRANSPORT=gmail_api일 때 pipeline/deliver.py가 이 모듈로 보낸다 (기본 smtp는 그대로)
- 관리자가 한 번 /admin/gmail/connect로 연결하면 refresh_token이 app_secrets 표에 암호화돼 저장된다
  (SESSION_SECRET에서 파생한 키 + AES-GCM. DB만 봐서는 원문을 알 수 없다)
- 보낼 때마다: refresh_token -> access token(만료 전까지 이 프로세스 안에서 재사용) -> messages.send {"raw": base64url(메시지)}
- 실패는 GmailError. 429·5xx는 한 번 다시 시도한다. invalid_grant(동의 취소·만료)는 다시 연결하라는 문구로 알린다
- 토큰·키 값은 로그와 오류 문구에 쓰지 않는다
"""
import base64
import logging
import os
import secrets
import time
from datetime import datetime
from email.message import EmailMessage

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

import db
from routes import tokens

log = logging.getLogger("toolscout.gmail_api")

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SECRET_NAME = "gmail_refresh_token"
RECONNECT = "Gmail 연결이 끊김, /admin/gmail/connect로 다시 연결"
NOT_CONNECTED = "Gmail 연결 안 됨, /admin/gmail/connect로 연결"
TIMEOUT = 20
_post = httpx.post  # 검수에서 가짜 구글로 바꿔 끼운다 (routes/google.py의 _post와 같은 방식)
_sleep = time.sleep  # 검수에서 기다림 없이 돌리려고 바꿔 끼운다
_access: dict = {"token": "", "exp": 0.0}  # 프로세스 안 access token 보관


class GmailError(Exception):
    pass


# ----- 암호화 보관 -----
def _box(name: str) -> AESGCM:
    return AESGCM(tokens.derive("app_secrets", name))  # 32바이트 = AES-256


def encrypt(name: str, value: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.urlsafe_b64encode(nonce + _box(name).encrypt(nonce, value.encode(), name.encode())).decode()


def decrypt(name: str, stored: str) -> str | None:
    """키(SESSION_SECRET)가 바뀌었거나 값이 깨졌으면 None."""
    try:
        raw = base64.urlsafe_b64decode(stored.encode())
        return _box(name).decrypt(raw[:12], raw[12:], name.encode()).decode()
    except (InvalidTag, ValueError):
        return None


def save_refresh_token(refresh_token: str) -> None:
    """저장(이미 있으면 갱신). 보관 중인 access token은 버린다."""
    values = {"name": SECRET_NAME, "value_encrypted": encrypt(SECRET_NAME, refresh_token), "updated_at": db.utcnow()}
    statement = insert(db.AppSecret).values(**values).on_conflict_do_update(
        index_elements=["name"], set_={"value_encrypted": values["value_encrypted"], "updated_at": values["updated_at"]})
    with db.get_engine().begin() as connection:
        connection.execute(statement)
    _access.update(token="", exp=0.0)


def _row() -> db.AppSecret | None:
    with db.session() as s:
        return s.exec(select(db.AppSecret).where(db.AppSecret.name == SECRET_NAME)).first()


def refresh_token() -> str | None:
    row = _row()
    return decrypt(SECRET_NAME, row.value_encrypted) if row else None


def connection_status() -> dict:
    """{connected, connected_at}. 저장돼 있고 지금 키로 풀리는 것만 연결됨."""
    row = _row()
    ok = bool(row and decrypt(SECRET_NAME, row.value_encrypted))
    at: datetime | None = row.updated_at if ok else None
    return {"connected": ok, "connected_at": at.isoformat() if at else None}


# ----- 보내기 -----
def _request(url: str, **kwargs):
    """_post 한 번. 429·5xx면 잠깐 쉬고 한 번만 다시. 네트워크 오류도 한 번 다시."""
    for attempt in (1, 2):
        try:
            response = _post(url, timeout=TIMEOUT, **kwargs)
        except (httpx.HTTPError, OSError) as exc:
            if attempt == 2:
                raise GmailError(f"Gmail API 연결 실패 ({type(exc).__name__})") from exc
        else:
            if (response.status_code == 429 or response.status_code >= 500) and attempt == 1:
                _sleep(2)
                continue
            return response
        _sleep(2)
    raise GmailError("Gmail API 연결 실패")  # 도달하지 않음


def access_token() -> str:
    """만료 1분 전까지는 보관한 것을 다시 쓴다."""
    if _access["token"] and _access["exp"] > time.time() + 60:
        return _access["token"]
    refresh = refresh_token()
    if not refresh:
        raise GmailError(NOT_CONNECTED)
    response = _request(TOKEN_URL, data={"client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
                                         "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
                                         "refresh_token": refresh, "grant_type": "refresh_token"})
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code != 200 or not body.get("access_token"):
        if body.get("error") == "invalid_grant":
            raise GmailError(RECONNECT)
        raise GmailError(f"Gmail 토큰 받기 실패 (HTTP {response.status_code} {str(body.get('error', ''))[:40]})")
    _access.update(token=body["access_token"], exp=time.time() + int(body.get("expires_in") or 3600))
    return _access["token"]


def send_message(message: EmailMessage) -> None:
    """EmailMessage 한 통을 보낸다. 실패하면 GmailError."""
    payload = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
    for attempt in (1, 2):
        response = _request(SEND_URL, json=payload, headers={"Authorization": f"Bearer {access_token()}"})
        if response.status_code == 401 and attempt == 1:  # 보관한 access token이 일찍 끝났을 때 한 번만 새로 받는다
            _access.update(token="", exp=0.0)
            continue
        break
    if response.status_code != 200:
        raise GmailError(f"Gmail 발송 실패 (HTTP {response.status_code})")


class GmailApiMailer:
    """smtplib.SMTP_SSL 자리에 끼우는 모양(with·login·send_message). deliver.py의 발송 코드를 그대로 쓰려고 맞췄다."""

    def __init__(self, host=None, port=None, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        return None

    def send_message(self, message: EmailMessage):
        send_message(message)
