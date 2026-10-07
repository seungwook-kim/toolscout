"""웹 검수 공통: 앱을 프로세스 안에서 띄우고(TestClient), 메일은 폴더로 받고, 검수용 사용자를 만들고 지운다.

- 예약은 끄고(SCHEDULER_ENABLED=0), 메일은 MAIL_FAKE_DIR로 보낸다 (실제 발송 없음)
- 검수용 사용자 주소는 web-*@toolscout.test. ADMIN_EMAILS에 넣어 개발 모드 회원가입 인증번호를 받게 한다(2026-10-08)
- 끝나면 검수용 사용자와 그 사람의 weights·seen·feedback·questions·briefings를 지운다
- 로그인한 검수용 사용자는 승인(status approved) 상태로 둔다. 승인 대기 상태가 필요하면 login(..., approve=False)
"""
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote

TEST_DOMAIN = "@toolscout.test"
MAIL_DIR = Path(tempfile.mkdtemp(prefix="toolscout_web_mail_"))
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["MAIL_FAKE_DIR"] = str(MAIL_DIR)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

import db  # noqa: E402


# APP_BASE_URL이 https면 세션 쿠키가 secure로 발급돼 http 요청에는 실리지 않는다(브라우저와 같은 규칙).
# 검수 클라이언트도 https로 요청해 배포 설정과 로컬 설정 어느 쪽에서도 로그인이 되게 한다 (2026-09-21)
BASE_URL = "https://testserver"


def admin_emails(*emails: str) -> None:
    current = [e for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    os.environ["ADMIN_EMAILS"] = ",".join(dict.fromkeys(current + list(emails)))


def client() -> TestClient:
    """with로 쓰면 앱 lifespan(MCP 세션 관리자)이 돈다. 프로세스에서 한 번만 with로 연다."""
    import main

    return TestClient(main.app, base_url=BASE_URL)


def second_client() -> TestClient:
    """두 번째 사용자용. lifespan 없이 쿠키 저장소만 따로 쓴다 (MCP 세션 관리자는 한 번만 돌릴 수 있다)."""
    import main

    return TestClient(main.app, base_url=BASE_URL)


def mails() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(MAIL_DIR.glob("*.json"))]


def last_link(to: str) -> str:
    for mail in reversed(mails()):
        if to in mail["to"]:
            match = re.search(r"token=([^\s]+)", mail["text"])
            return unquote(match.group(1)) if match else ""
    return ""


TEST_PASSWORD = "web-test-pass-1234"


def last_code(to: str) -> str:
    """가장 최근 회원가입 인증번호 메일의 6자리."""
    for mail in reversed(mails()):
        if to in mail["to"]:
            match = re.search(r"인증번호: (\d{6})", mail["text"])
            if match:
                return match.group(1)
    return ""


def login(c: TestClient, email: str, approve: bool = True) -> None:
    """회원가입(인증번호 받기 → 확인 → 비밀번호)으로 세션을 만든다. 이미 비밀번호가 있으면 비밀번호로 로그인 (2026-10-08).
    개발 모드는 관리자 주소만 가입할 수 있어 ADMIN_EMAILS에 넣는다. 관리자 가입은 바로 승인되므로 users 상태는 여기서 다시 맞춘다:
    기본은 승인, 승인 대기 검수(tests/access)만 approve=False. users.is_admin은 끈다(관리자 여부는 ADMIN_EMAILS로 본다)."""
    admin_emails(email)
    if c.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD}).status_code != 200:
        with db.get_engine().begin() as conn:  # 같은 주소를 다시 받을 때 60초 제한에 걸리지 않게
            conn.execute(delete(db.EmailCode).where(db.EmailCode.email == email))
        sent = c.post("/api/auth/signup/code", json={"email": email})
        assert sent.status_code == 200, sent.text
        verified = c.post("/api/auth/signup/verify", json={"email": email, "code": last_code(email)})
        assert verified.status_code == 200, verified.text
        done = c.post("/api/auth/signup/complete", json={"signup_token": verified.json()["signup_token"], "password": TEST_PASSWORD})
        assert done.status_code == 200, done.text
    set_user(email, status="approved" if approve else "pending")


def set_user(email: str, status: str) -> None:
    with db.session() as s:
        user = s.exec(select(db.User).where(db.User.email == email)).scalars().first()
        if user is not None:
            user.status, user.is_admin = status, False
            s.commit()


def approve_user(email: str) -> None:
    """검수용 사용자를 승인 상태로."""
    set_user(email, "approved")


def user_id(email: str) -> int | None:
    with db.get_engine().connect() as conn:
        row = conn.execute(select(db.User.id).where(db.User.email == email)).first()
    return row[0] if row else None


def cleanup_users(prefix: str = "web-") -> int:
    with db.get_engine().begin() as conn:
        ids = [r[0] for r in conn.execute(select(db.User.id).where(db.User.email.like(f"{prefix}%{TEST_DOMAIN}")))]
        if ids:
            for table in (db.Weight, db.Seen, db.Feedback, db.Question, db.Briefing):
                conn.execute(delete(table).where(table.user_id.in_(ids)))
            conn.execute(delete(db.User).where(db.User.id.in_(ids)))
        conn.execute(delete(db.EmailCode).where(db.EmailCode.email.like(f"{prefix}%{TEST_DOMAIN}")))
    return len(ids)
