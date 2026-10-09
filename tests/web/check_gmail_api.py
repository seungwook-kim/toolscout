"""Gmail API 발송 검수 (2026-10-09 사용자 결정 "Gmail API로 보내기": Railway가 바깥 SMTP를 막아서).
앱을 프로세스 안에서 띄우고 구글은 가짜로 바꿔 끼운다. 실제 구글 호출·실제 메일 발송 없음.

실행: uv run python -m tests.web.check_gmail_api
- 연결(관리자 전용, 같은 콜백 /auth/google/callback): 로그인 안 했으면 /login, 관리자 아니면 403, 동의 화면 주소(gmail.send·offline·consent,
  include_granted_scopes 없음), state 종류가 gmail이면 연결로 처리, 이메일이 GMAIL_USER와 다르면 저장 안 함, refresh_token 없으면 안내,
  토큰은 암호화돼 DB에 원문 없음, 다시 연결하면 갱신, 관리자 세션 없이 온 콜백은 거부, 로그인 흐름 state는 연결을 건드리지 않음
- 발송: MAIL_TRANSPORT 선택(기본 smtp), raw가 올바른 MIME(한글 제목·받는 사람·텍스트+HTML), access token 재사용·만료되면 새로·401이면 새로,
  invalid_grant 안내, 429·5xx는 한 번 재시도, 연결 안 됨은 config_missing(기록 안 함), 한 명 실패해도 나머지 발송,
  send_day mode=gmail_api·sent_at 기록, send_alert도 같은 길
- 원래 있던 gmail_refresh_token 행이 있으면 끝나고 그대로 되돌린다
"""
import base64
import email as email_lib
import json
import os
import sys
from contextlib import contextmanager
from datetime import date
from email import policy
from urllib.parse import parse_qs, urlsplit

from tests.web import common  # noqa: F401  환경변수를 먼저 채운다

from sqlalchemy import delete, insert, select  # noqa: E402

import db  # noqa: E402
from pipeline import deliver, gmail_api  # noqa: E402
from routes import google  # noqa: E402

ADMIN = "web-gmail-admin@toolscout.test"
OTHER = "web-gmail-other@toolscout.test"
U1 = "web-gmail-u1@toolscout.test"
U2 = "web-gmail-u2@toolscout.test"
SENDER = "web-gmail-sender@toolscout.test"
DAY = date(2000, 1, 9)


@contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class Fake:
    def __init__(self, status: int, body: dict | None = None):
        self.status_code, self.body = status, body or {}

    def json(self):
        return self.body


def secret_row() -> db.AppSecret | None:
    with db.session() as s:
        return s.exec(select(db.AppSecret).where(db.AppSecret.name == gmail_api.SECRET_NAME)).scalars().first()


def clear_secret() -> None:
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.AppSecret).where(db.AppSecret.name == gmail_api.SECRET_NAME))
    gmail_api._access.update(token="", exp=0.0)


def start_connect(c):
    resp = c.get("/admin/gmail/connect", follow_redirects=False)
    state = parse_qs(urlsplit(resp.headers["location"]).query).get("state", [""])[0] if resp.status_code == 303 else ""
    return resp, state


def fake_connect_google(email: str, refresh: str | None, scope: str = "https://www.googleapis.com/auth/gmail.send openid email"):
    body = {"id_token": "fake-id-token", "scope": scope} | ({"refresh_token": refresh} if refresh else {})
    google._post = lambda url, data, timeout: Fake(200, body)
    google._get = lambda url, params, timeout: Fake(200, {"aud": "client-id", "iss": "https://accounts.google.com", "email_verified": "true",
                                                         "email": email, "sub": "sub-x"})


def connect_checks(c, c_other) -> dict:
    anon = common.second_client().get("/admin/gmail/connect", follow_redirects=False)
    other = c_other.get("/admin/gmail/connect", follow_redirects=False)
    anon_status = common.second_client().get("/api/admin/gmail")
    other_status = c_other.get("/api/admin/gmail")
    before = c.get("/api/admin/gmail").json()
    resp, state = start_connect(c)
    query = parse_qs(urlsplit(resp.headers["location"]).query)
    cookie_ok = resp.headers.get("set-cookie", "").startswith(f"{google.STATE_COOKIE}=")

    def callback(client, st, code="x"):
        return client.get(f"/auth/google/callback?code={code}&state={st}", follow_redirects=False)

    fake_connect_google(SENDER, "refresh-token-ONE")
    done = callback(c, state)
    row = secret_row()
    first_at = row.updated_at if row else None
    status = c.get("/api/admin/gmail").json()
    # 다른 계정이면 저장 안 함(기존 값 유지)
    _, state2 = start_connect(c)
    fake_connect_google("someone-else@example.test", "refresh-token-EVIL")
    wrong = callback(c, state2)
    still = gmail_api.refresh_token()
    # refresh_token이 없으면 안내
    _, state3 = start_connect(c)
    fake_connect_google(SENDER, None)
    no_refresh = callback(c, state3)
    # 관리자 세션 없이 온 콜백은 거부
    _, state4 = start_connect(c)
    fake_connect_google(SENDER, "refresh-token-NOSESSION")
    no_session = callback(common.second_client(), state4)
    c_no = common.second_client()
    c_no.cookies.set(google.STATE_COOKIE, state4)
    no_session = callback(c_no, state4)
    # 다시 연결하면 갱신
    _, state5 = start_connect(c)
    fake_connect_google(SENDER, "refresh-token-TWO")
    again = callback(c, state5)
    row2 = secret_row()
    # 로그인 흐름 state(k 없음)는 연결로 처리되지 않는다
    login_start = c.get("/auth/google", follow_redirects=False)
    login_state = parse_qs(urlsplit(login_start.headers["location"]).query)["state"][0]
    fake_connect_google(ADMIN, "refresh-token-LOGIN")
    login_cb = callback(c, login_state)
    after_login = gmail_api.refresh_token()
    page = c.get("/admin/invites")
    return {
        "연결_로그인안함은_/login": anon.status_code == 303 and anon.headers["location"] == "/login",
        "연결_관리자아니면_403": other.status_code == 403 and anon_status.status_code == 401 and other_status.status_code == 403,
        "연결_동의화면_gmail.send·offline·consent": resp.status_code == 303 and resp.headers["location"].startswith(google.AUTH_URL)
        and query["scope"] == ["https://www.googleapis.com/auth/gmail.send openid email"] and query["access_type"] == ["offline"]
        and query["prompt"] == ["consent"] and "include_granted_scopes" not in query and query["redirect_uri"][0].endswith("/auth/google/callback")
        and cookie_ok,
        "연결_전_상태는_안됨": before["connected"] is False and before["connected_at"] is None,
        "연결_state_종류가_gmail이면_연결로_처리": done.status_code == 303 and done.headers["location"] == "/admin/invites?gmail=connected"
        and gmail_api.refresh_token() is not None,
        "연결_토큰은_암호화(DB에_원문없음)": row is not None and "refresh-token-ONE" not in row.value_encrypted
        and b"refresh-token-ONE" not in base64.urlsafe_b64decode(row.value_encrypted.encode()),
        "연결_상태_API": status["connected"] is True and bool(status["connected_at"]) and status["transport"] in ("smtp", "gmail_api")
        and status["sender_set"] is True and "refresh" not in json.dumps(status),
        "연결_이메일_다르면_저장안함": wrong.headers["location"] == "/admin/invites?gmail=wrong_account" and still == "refresh-token-ONE",
        "연결_refresh_token_없으면_안내": no_refresh.headers["location"] == "/admin/invites?gmail=no_refresh" and still == "refresh-token-ONE",
        "연결_관리자_세션없으면_거부": no_session.headers["location"] == "/login?error=google_failed" and gmail_api.refresh_token() != "refresh-token-NOSESSION",
        "연결_다시하면_갱신": again.headers["location"] == "/admin/invites?gmail=connected" and gmail_api.refresh_token() == "refresh-token-TWO"
        and row2.updated_at >= first_at,
        "로그인흐름_state는_연결을_안건드림": login_cb.status_code == 303 and not login_cb.headers["location"].startswith("/admin/invites?gmail")
        and after_login == "refresh-token-TWO",
        "관리자화면에_연결줄": page.status_code == 200 and "gm-line" in page.text and "/api/admin/gmail" in page.text,
    }


class FakeGoogle:
    """gmail_api._post 대신. 토큰 받기와 messages.send를 흉내 낸다. rules로 순서대로 응답을 바꾼다."""

    def __init__(self):
        self.token_calls, self.sends = 0, []
        self.token_replies: list = []  # 앞에서부터 하나씩 쓴다 (없으면 정상 응답)
        self.send_replies: list = []
        self.fail_to: str | None = None  # 이 문구가 받는 사람에 있으면 항상 500

    def __call__(self, url, timeout=None, data=None, json=None, headers=None):
        if url == gmail_api.TOKEN_URL:
            self.token_calls += 1
            if self.token_replies:
                return self.token_replies.pop(0)
            return Fake(200, {"access_token": f"access-{self.token_calls}", "expires_in": 3600})
        raw = email_lib.message_from_bytes(base64.urlsafe_b64decode(json["raw"]), policy=policy.default)
        if self.fail_to and self.fail_to in (raw["To"] or ""):
            self.sends.append({"auth": headers["Authorization"], "to": raw["To"], "status": 500})
            return Fake(500, {"error": {"code": 500}})
        reply = self.send_replies.pop(0) if self.send_replies else Fake(200, {"id": "m1"})
        self.sends.append({"auth": headers["Authorization"], "raw": json["raw"], "to": raw["To"], "status": reply.status_code})
        return reply


def seed_day(user_ids: list[int]) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.Briefing).where(db.Briefing.date == DAY))
        for uid in user_ids:
            conn.execute(insert(db.Briefing).values(user_id=uid, date=DAY, item_id=None, rank=0, card_json=None,
                                                    empty_reason="후보 1건 모두 빠짐 (반려 1, 검증 제외 0, 형식 실패 0)", trace_id=f"t{uid}"))


def sent_at_of(uid: int):
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.Briefing.sent_at).where(db.Briefing.user_id == uid, db.Briefing.date == DAY)).scalar()


def send_checks() -> dict:
    fake = FakeGoogle()
    gmail_api._post, gmail_api._sleep = fake, lambda s: None
    out: dict = {}
    base = dict(GMAIL_USER=SENDER, GOOGLE_CLIENT_ID="client-id", GOOGLE_CLIENT_SECRET="secret", ADMIN_EMAILS="web-gmail-adm@example.test",
                DEV_MODE="0")
    with env(**base, MAIL_FAKE_DIR=None, MAIL_TRANSPORT=None):
        out["발송방식_기본은_smtp"] = deliver.transport() == "smtp" and deliver.default_smtp_factory().__name__ == "SMTP_SSL"
    with env(**base, MAIL_FAKE_DIR=None, MAIL_TRANSPORT="gmail_api"):
        out["발송방식_gmail_api"] = deliver.transport() == "gmail_api" and deliver.default_smtp_factory() is gmail_api.GmailApiMailer
    with env(**base, MAIL_TRANSPORT="gmail_api"):  # MAIL_FAKE_DIR이 있으면(검수) 폴더로만
        out["검수_MAIL_FAKE_DIR이_우선"] = deliver.default_smtp_factory() is deliver.DirMailer
    with env(**base, MAIL_FAKE_DIR=None, MAIL_TRANSPORT="gmail_api"):
        # 연결 안 됨
        clear_secret()
        try:
            deliver.send_single(["a@example.test"], "제목", "본문")
            not_connected = ""
        except deliver.MailError as exc:
            not_connected = str(exc)
        out["연결안됨_send_single_MailError"] = "연결 안 됨" in not_connected and fake.token_calls == 0
        users = []
        with db.session() as s:
            for mail in (U1, U2):
                user = db.User(email=mail, role="", status="approved")
                s.add(user)
                s.commit()
                s.refresh(user)
                users.append(user.id)
        seed_day(users)
        none = deliver.send_day(DAY)
        out["연결안됨_send_day_config_missing·기록안함"] = none["mode"] == "config_missing" and none["sent"] == [] and sent_at_of(users[0]) is None \
            and all("연결 안 됨" in f["error"] for f in none["failed"]) and len(none["failed"]) == 2
        alert_none = deliver.send_alert("검수", ["검수"])
        out["연결안됨_알림은_mail_error(로그만)"] = alert_none == "mail_error"

        gmail_api.save_refresh_token("refresh-for-send")
        # 올바른 MIME, 한글 제목, 받는 사람, access token 재사용
        deliver.send_single(["받는사람@example.test", "b@example.test"], "한글 제목 검수", "본문 텍스트 가나다", "<p>HTML 본문 라마바</p>")
        deliver.send_single(["c@example.test"], "두 번째", "본문")
        sent = email_lib.message_from_bytes(base64.urlsafe_b64decode(fake.sends[0]["raw"]), policy=policy.default)
        out["raw_올바른_MIME·한글제목·받는사람"] = sent["Subject"] == "한글 제목 검수" and "받는사람@example.test" in sent["To"] \
            and "b@example.test" in sent["To"] and SENDER in sent["From"]
        out["raw_텍스트+HTML"] = "본문 텍스트 가나다" in sent.get_body(("plain",)).get_content() \
            and "HTML 본문 라마바" in sent.get_body(("html",)).get_content()
        out["access_token_재사용"] = fake.token_calls == 1 and [x["auth"] for x in fake.sends] == ["Bearer access-1", "Bearer access-1"]
        gmail_api._access["exp"] = 0.0  # 만료
        deliver.send_single(["d@example.test"], "세 번째", "본문")
        out["만료되면_새로_받음"] = fake.token_calls == 2 and fake.sends[-1]["auth"] == "Bearer access-2"
        fake.send_replies = [Fake(401, {"error": {}})]
        deliver.send_single(["e@example.test"], "네 번째", "본문")
        out["401이면_새_token으로_한번_다시"] = fake.token_calls == 3 and fake.sends[-1]["auth"] == "Bearer access-3" and fake.sends[-1]["status"] == 200
        # 429 재시도
        count = len(fake.sends)
        fake.send_replies = [Fake(429, {})]
        deliver.send_single(["f@example.test"], "다섯 번째", "본문")
        out["429는_한번_재시도"] = len(fake.sends) == count + 2 and fake.sends[-1]["status"] == 200
        fake.send_replies = [Fake(503, {}), Fake(503, {})]
        try:
            deliver.send_single(["g@example.test"], "여섯 번째", "본문")
            twice = ""
        except deliver.MailError as exc:
            twice = str(exc)
        out["5xx가_두번이면_실패"] = "HTTP 503" in twice
        # invalid_grant
        gmail_api._access.update(token="", exp=0.0)
        fake.token_replies = [Fake(400, {"error": "invalid_grant"})]
        try:
            deliver.send_single(["h@example.test"], "일곱 번째", "본문")
            grant = ""
        except deliver.MailError as exc:
            grant = str(exc)
        out["invalid_grant는_다시연결_안내"] = "다시 연결" in grant and "/admin/gmail/connect" in grant
        # send_day: 한 명 실패해도 나머지 발송
        seed_day(users)
        fake.sends.clear()
        fake.fail_to = U1
        partial = deliver.send_day(DAY)
        out["send_day_mode=gmail_api·한명_실패해도_나머지"] = partial["mode"] == "gmail_api" and partial["sent"] == [users[1]] \
            and [f["user_id"] for f in partial["failed"]] == [users[0]] and partial["mails"] == 2 and partial["rows_marked"] == 1
        out["sent_at_성공한_사람만"] = sent_at_of(users[1]) is not None and sent_at_of(users[0]) is None
        out["받는사람은_users.email"] = any(x["to"] == U2 and x["status"] == 200 for x in fake.sends)
        fake.fail_to = None
        retry = deliver.send_day(DAY)
        out["다시_보내면_남은_사람만"] = retry["sent"] == [users[0]] and sent_at_of(users[0]) is not None and deliver.send_day(DAY)["messages"] == 0
        # send_day에서 연결이 끊겼을 때
        seed_day(users)
        gmail_api._access.update(token="", exp=0.0)
        fake.token_replies = [Fake(400, {"error": "invalid_grant"})] * 2
        broken = deliver.send_day(DAY)
        out["send_day_연결끊김_사유·기록안함"] = broken["sent"] == [] and len(broken["failed"]) == 2 \
            and all("다시 연결" in f["error"] for f in broken["failed"]) and sent_at_of(users[0]) is None
        # 실패 알림도 같은 길
        fake.sends.clear()
        gmail_api._access.update(token="", exp=0.0)
        alert = deliver.send_alert("검수 알림", ["내용"])
        out["send_alert_같은_길"] = alert == "sent" and fake.sends[-1]["to"] == "web-gmail-adm@example.test"
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.Briefing).where(db.Briefing.date == DAY))
    return out


def main() -> int:
    common.cleanup_users("web-gmail-")
    common.admin_emails(ADMIN)
    old = secret_row()
    saved = (google._post, google._get, gmail_api._post, gmail_api._sleep)
    try:
        with env(GMAIL_USER=SENDER, GOOGLE_CLIENT_ID="client-id", GOOGLE_CLIENT_SECRET="secret"):
            clear_secret()
            with common.client() as c:
                common.login(c, ADMIN)
                c_other = common.second_client()
                common.login(c_other, OTHER)  # 로그인(가입)하려면 관리자 주소여야 해서 넣었다가
                os.environ["ADMIN_EMAILS"] = ",".join(e for e in os.environ["ADMIN_EMAILS"].split(",") if e != OTHER)  # 바로 뺀다
                checks = connect_checks(c, c_other)
        checks |= send_checks()
    finally:
        google._post, google._get, gmail_api._post, gmail_api._sleep = saved
        with db.get_engine().begin() as conn:
            conn.execute(delete(db.AppSecret).where(db.AppSecret.name == gmail_api.SECRET_NAME))
            if old is not None:
                conn.execute(insert(db.AppSecret).values(name=old.name, value_encrypted=old.value_encrypted, updated_at=old.updated_at))
            conn.execute(delete(db.Briefing).where(db.Briefing.date == DAY))
        removed = common.cleanup_users("web-gmail-")
    checks["검수용_사용자_정리"] = removed >= 4
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
