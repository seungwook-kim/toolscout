"""로그인·회원가입 검수 (2026-10-08 사용자 결정: 첫 화면은 회원가입 + 구글 로그인, 아이디 = 이메일, 인증번호 확인 뒤 가입,
비밀번호 로그인, 관리자 승인 뒤 사용). 앱을 프로세스 안에서 띄우고 메일은 폴더로 받는다. 실제 발송·구글 호출 없음(가짜 구글).

실행: uv run python -m tests.web.check_auth
- 가입: 형식 400, 개발 모드 관리자 아닌 주소 403, 인증번호 메일(6자리, DB에는 해시만), 60초 안 재요청 429, 1시간 5번 넘으면 429,
  틀린 번호 400(남은 횟수), 5번 틀리면 429, 맞으면 가입 토큰, 약한 비밀번호 400, 가입 → 세션, 같은 토큰 다시 400, 이미 가입한 주소 409
- 관리자 주소 가입은 바로 승인, 운영 모드 일반 주소 가입은 승인 대기(/pending) + 관리자 알림 메일, 승인 대기는 화면 /pending·API 403
- 비밀번호 로그인: 틀리면 같은 말 400, 5번이면 15분 잠금 429, 맞으면 갈 화면. 예전 링크 계정(비밀번호 없음)은 인증 뒤 비밀번호를 정해 이어 씀
- 구글: 설정 없으면 버튼 숨김·/auth/google은 google_off, 있으면 동의 화면으로(state 쿠키), state 틀리면 실패, aud 다르면 실패,
  맞으면 계정 생성(google_sub), 같은 구글 계정은 같은 사용자, 같은 이메일 계정에는 붙임, 개발 모드 관리자 아닌 주소는 dev_only
- 서명 토큰 로그인(/auth/verify, 검수·도구용): 만료·재사용·위조 거부 / 세션 쿠키 변조 401 / 로그아웃
"""
import json
import os
import sys
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from tests.web import common  # noqa: F401  환경변수를 먼저 채운다

from sqlalchemy import insert, select, update  # noqa: E402

import db  # noqa: E402
from routes import auth, google, tokens  # noqa: E402

A = "web-auth-a@toolscout.test"  # 관리자 주소로 가입
B = "web-auth-b@toolscout.test"  # 운영 모드 일반 가입
C = "web-auth-c@toolscout.test"  # 예전 링크 계정
G = "web-auth-g@toolscout.test"  # 구글 관리자
G2 = "web-auth-g2@toolscout.test"  # 구글 일반 (운영 모드)
OUTSIDER = "web-auth-outsider@toolscout.test"
PASSWORD = "good-pass-123"


@contextmanager
def env(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update({k: v for k, v in values.items() if v is not None})
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def user(email: str) -> db.User | None:
    with db.session() as s:
        return s.exec(select(db.User).where(db.User.email == email)).scalars().first()


def signup(c, email: str, password: str = PASSWORD):
    c.post("/api/auth/signup/code", json={"email": email})
    token = c.post("/api/auth/signup/verify", json={"email": email, "code": common.last_code(email)}).json()["signup_token"]
    return c.post("/api/auth/signup/complete", json={"signup_token": token, "password": password})


class Fake:
    def __init__(self, status: int, body: dict):
        self.status_code, self.body = status, body

    def json(self):
        return self.body


def fake_google(email: str, sub: str, aud: str = "client-id"):
    google._post = lambda url, data, timeout: Fake(200, {"id_token": "fake-id-token"})
    google._get = lambda url, params, timeout: Fake(200, {"aud": aud, "iss": "https://accounts.google.com", "email_verified": "true",
                                                         "email": email, "sub": sub})


def google_login(c, email: str, sub: str, aud: str = "client-id", state_ok: bool = True):
    fake_google(email, sub, aud)
    start = c.get("/auth/google", follow_redirects=False)
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    return start, c.get(f"/auth/google/callback?code=x&state={state if state_ok else state + 'x'}", follow_redirects=False)


def main() -> int:
    common.cleanup_users("web-auth-")
    common.admin_emails(A, C, G)
    saved_google = (google._post, google._get)
    try:
        with common.client() as c:
            # 가입 (개발 모드)
            bad_email = c.post("/api/auth/signup/code", json={"email": "메일아님"})
            outsider = c.post("/api/auth/signup/code", json={"email": OUTSIDER})
            sent = c.post("/api/auth/signup/code", json={"email": A})
            again = c.post("/api/auth/signup/code", json={"email": A})
            code = common.last_code(A)
            with db.session() as s:
                stored = s.exec(select(db.EmailCode).where(db.EmailCode.email == A)).scalars().all()
            wrong = c.post("/api/auth/signup/verify", json={"email": A, "code": "000000" if code != "000000" else "111111"})
            right = c.post("/api/auth/signup/verify", json={"email": A, "code": code})
            token = right.json().get("signup_token", "")
            weak = c.post("/api/auth/signup/complete", json={"signup_token": token, "password": "short1"})
            letters = c.post("/api/auth/signup/complete", json={"signup_token": token, "password": "onlyletters"})
            no_session = c.get("/api/me")
            done = c.post("/api/auth/signup/complete", json={"signup_token": token, "password": PASSWORD})
            session_cookie = c.cookies.get(auth.SESSION_COOKIE)
            me = c.get("/api/me")
            reused = c.post("/api/auth/signup/complete", json={"signup_token": token, "password": PASSWORD})
            taken = c.post("/api/auth/signup/code", json={"email": A})
            a_user = user(A)
            # 비밀번호 로그인
            c.post("/api/auth/logout")
            fails = [c.post("/api/auth/login", json={"email": A, "password": "wrong-pass-1"}) for _ in range(5)]
            locked = c.post("/api/auth/login", json={"email": A, "password": PASSWORD})
            unknown = c.post("/api/auth/login", json={"email": "web-auth-none@toolscout.test", "password": PASSWORD})
            with db.get_engine().begin() as conn:
                conn.execute(update(db.User).where(db.User.email == A).values(login_locked_until=None))
            ok_login = c.post("/api/auth/login", json={"email": A, "password": PASSWORD})
            login_page = c.get("/login", follow_redirects=False)
            # 틀린 번호 5번이면 다시 받아야
            c.post("/api/auth/logout")
            c.post("/api/auth/signup/code", json={"email": C})
            five = [c.post("/api/auth/signup/verify", json={"email": C, "code": "999999"}) for _ in range(5)]
            after_five = c.post("/api/auth/signup/verify", json={"email": C, "code": common.last_code(C)})
            # 1시간 5번 상한
            with db.get_engine().begin() as conn:
                conn.execute(update(db.EmailCode).where(db.EmailCode.email == C).values(created_at=db.utcnow() - timedelta(minutes=5)))
                for _ in range(4):
                    conn.execute(insert(db.EmailCode).values(email=C, code_hash="x", attempts=0, created_at=db.utcnow() - timedelta(minutes=5),
                                                             expires_at=db.utcnow()))
            hourly = c.post("/api/auth/signup/code", json={"email": C})
            # 예전 링크 계정(비밀번호 없음)은 인증 뒤 이어 씀
            with db.get_engine().begin() as conn:
                conn.execute(db.EmailCode.__table__.delete().where(db.EmailCode.email == C))
            link_login = c.get(f"/auth/verify?token={tokens.sign('login', {'email': C}, 600)}", follow_redirects=False)
            legacy_id = common.user_id(C)
            c.post("/api/auth/logout")
            legacy = signup(c, C)
            legacy_user = user(C)
            # 운영 모드 일반 가입 → 승인 대기 + 관리자 알림
            c.post("/api/auth/logout")
            with env(DEV_MODE="0"):
                pending = signup(c, B)
                pending_root = c.get("/", follow_redirects=False)
                pending_page = c.get("/pending", follow_redirects=False)
                pending_api = c.get("/api/briefings/today")
                pending_me = c.get("/api/me").json()
            notices = [m for m in common.mails() if "새 가입 신청" in m["subject"] and B in m["text"]]
            # 구글
            c.post("/api/auth/logout")
            off_options = c.get("/api/auth/options").json()
            off = c.get("/auth/google", follow_redirects=False)
            with env(GOOGLE_CLIENT_ID="client-id", GOOGLE_CLIENT_SECRET="client-secret"):
                on_options = c.get("/api/auth/options").json()
                start, g_first = google_login(c, G, "g-sub-1")
                query = parse_qs(urlsplit(start.headers["location"]).query)
                g_user = user(G)
                c.post("/api/auth/logout")
                _, g_again = google_login(c, G, "g-sub-1")
                g_count = len([u for u in [user(G)] if u])
                c.post("/api/auth/logout")
                _, bad_state = google_login(c, G, "g-sub-1", state_ok=False)
                _, bad_aud = google_login(c, G, "g-sub-1", aud="someone-else")
                _, link_a = google_login(c, A, "g-sub-a")
                a_linked = user(A)
                c.post("/api/auth/logout")
                _, dev_only = google_login(c, G2, "g-sub-2")
                with env(DEV_MODE="0"):
                    _, g2 = google_login(c, G2, "g-sub-2")
                g2_user = user(G2)
            # 서명 토큰 로그인과 세션
            c.post("/api/auth/logout")
            expired = c.get(f"/auth/verify?token={tokens.sign('login', {'email': A}, -1)}", follow_redirects=False)
            forged = c.get(f"/auth/verify?token={tokens.sign('login', {'email': A}, 600)[:-3]}abc", follow_redirects=False)
            once = tokens.sign("login", {"email": A}, 600)
            c.get(f"/auth/verify?token={once}", follow_redirects=False)
            used = c.get(f"/auth/verify?token={once}", follow_redirects=False)
            c.cookies.clear()
            c.cookies.set(auth.SESSION_COOKIE, session_cookie[:-2] + "zz", domain="testserver.local", path="/")
            tampered = c.get("/api/me")
            c.cookies.clear()
            c.cookies.set(auth.SESSION_COOKIE, session_cookie, domain="testserver.local", path="/")
            restored = c.get("/api/me")
            logout = c.post("/api/auth/logout")
            after_logout = c.get("/api/me")
            signup_page, landing = c.get("/signup"), c.get("/login")
            mail_texts = [m["text"] for m in common.mails() if A in m["to"]]
    finally:
        google._post, google._get = saved_google
        removed = common.cleanup_users("web-auth-")
    checks = {
        "가입_이메일_형식_틀리면_400": bad_email.status_code == 400,
        "개발모드_관리자_아닌_주소는_403": outsider.status_code == 403,
        "인증번호_메일_6자리·DB에는_해시만": sent.status_code == 200 and len(code) == 6 and len(stored) == 1
        and stored[0].code_hash != code and code not in stored[0].code_hash and "인증번호" in mail_texts[0],
        "60초_안_재요청은_429": again.status_code == 429,
        "틀린_번호는_400_남은_횟수": wrong.status_code == 400 and "남은 횟수 4" in wrong.json()["detail"],
        "맞는_번호면_가입_토큰": right.status_code == 200 and bool(token),
        "약한_비밀번호_400": weak.status_code == 400 and letters.status_code == 400,
        "가입_전_세션없으면_401": no_session.status_code == 401,
        "관리자_주소_가입은_바로_승인·설정으로": done.status_code == 200 and done.json()["next"] == "/settings" and bool(session_cookie)
        and a_user.status == "approved" and a_user.is_admin is True and a_user.password_hash.startswith("scrypt$")
        and PASSWORD not in a_user.password_hash,
        "세션으로_내정보·로그인방식": me.status_code == 200 and me.json()["email"] == A and me.json()["login"] == "password",
        "같은_가입_토큰_두번째는_400": reused.status_code == 400,
        "이미_가입한_주소는_409": taken.status_code == 409,
        "비밀번호_틀리면_400_같은말": all(f.status_code == 400 for f in fails) and unknown.status_code == 400
        and fails[0].json()["detail"] == unknown.json()["detail"],
        "5번_틀리면_잠금_429": locked.status_code == 429,
        "맞으면_로그인·로그인화면은_홈으로": ok_login.status_code == 200 and ok_login.json()["next"] == "/settings"
        and login_page.status_code == 303,
        "번호_5번_틀리면_다시_받아야": [r.status_code for r in five] == [400, 400, 400, 400, 429] and after_five.status_code == 429,
        "1시간_5번_넘으면_429": hourly.status_code == 429 and "1시간" in hourly.json()["detail"],
        "예전_링크_계정은_인증_뒤_비밀번호_정해_이어씀": link_login.status_code == 303 and legacy.status_code == 200
        and legacy_user.id == legacy_id and bool(legacy_user.password_hash),
        "운영모드_일반_가입은_승인대기": pending.status_code == 200 and pending.json()["next"] == "/pending" and pending.json()["status"] == "pending"
        and pending_root.headers.get("location") == "/pending" and pending_page.status_code == 200 and pending_api.status_code == 403
        and pending_me["approved"] is False,
        "새_가입_관리자_알림_메일": len(notices) == 1,
        "구글_설정없으면_버튼숨김·google_off": off_options["google"] is False and off.headers["location"] == "/login?error=google_off",
        "구글_동의화면으로_state·리디렉션": on_options["google"] is True and start.headers["location"].startswith(google.AUTH_URL)
        and query["client_id"] == ["client-id"] and query["redirect_uri"][0].endswith("/auth/google/callback")
        and query["scope"] == ["openid email profile"],
        "구글_첫_로그인_계정생성(관리자는_승인)": g_first.status_code == 303 and g_first.headers["location"] == "/settings"
        and g_user is not None and g_user.google_sub == "g-sub-1" and g_user.status == "approved",
        "같은_구글_계정은_같은_사용자": g_again.headers["location"] == "/settings" and g_count == 1,
        "state·aud_틀리면_실패": bad_state.headers["location"] == "/login?error=google_failed"
        and bad_aud.headers["location"] == "/login?error=google_failed",
        "같은_이메일_계정에_구글을_붙임": link_a.status_code == 303 and a_linked.id == a_user.id and a_linked.google_sub == "g-sub-a",
        "개발모드_관리자_아닌_구글은_dev_only": dev_only.headers["location"] == "/login?error=dev_only",
        "운영모드_구글_일반은_승인대기": g2.headers["location"] == "/pending" and g2_user is not None and g2_user.status == "pending",
        "서명토큰_만료·위조·재사용_거부": expired.headers["location"] == "/login?error=expired"
        and forged.headers["location"] == "/login?error=invalid" and used.headers["location"] == "/login?error=used",
        "변조_세션쿠키는_401": tampered.status_code == 401,
        "로그아웃하면_401": restored.status_code == 200 and logout.status_code == 200 and after_logout.status_code == 401,
        "첫화면·가입화면_200": landing.status_code == 200 and signup_page.status_code == 200,
        "검수용_사용자_정리": removed >= 5,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
