"""웹 검수 공통: 앱을 프로세스 안에서 띄우고(TestClient), 메일은 폴더로 받고, 검수용 사용자를 만들고 지운다.

- 예약은 끄고(SCHEDULER_ENABLED=0), 메일은 MAIL_FAKE_DIR로 보낸다 (실제 발송 없음)
- 검수용 사용자 주소는 web-*@toolscout.test. ADMIN_EMAILS에 넣어 개발 모드 로그인 링크를 받게 한다
- 끝나면 검수용 사용자와 그 사람의 weights·seen·feedback·questions·briefings를 지운다
- 로그인한 검수용 사용자는 승인(status approved) 상태로 둔다. 초대 대기 상태가 필요하면 login(..., approve=False)
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


def login(c: TestClient, email: str, approve: bool = True) -> None:
    """메일 링크를 받아 눌러 세션을 만든다. 가입은 초대제라 새 사용자는 pending이므로 기본으로 승인해 둔다 (2026-09-16).
    초대 검수(tests/access)만 approve=False로 대기 상태를 그대로 본다."""
    admin_emails(email)
    from routes import auth

    auth._last_request.pop(email, None)
    response = c.post("/api/auth/request", json={"email": email})
    assert response.status_code == 200, response.text
    c.get(f"/auth/verify?token={last_link(email)}", follow_redirects=False)
    if approve:
        approve_user(email)


def approve_user(email: str) -> None:
    """검수용 사용자를 승인 상태로 (초대 코드 없이)."""
    with db.session() as s:
        user = s.exec(select(db.User).where(db.User.email == email)).scalars().first()
        if user is not None:
            user.status = "approved"
            s.commit()


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
    return len(ids)
