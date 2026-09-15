"""로그인 검수 (이메일 매직링크, 세션). 앱을 프로세스 안에서 띄우고 메일은 폴더로 받는다. 실제 발송 없음.

실행: uv run python -m tests.web.check_auth
"""
import json
import sys

from tests.web import common  # noqa: F401  환경변수를 먼저 채운다

import db  # noqa: E402
from routes import auth, tokens  # noqa: E402

A = "web-auth-a@toolscout.test"
OUTSIDER = "web-auth-outsider@toolscout.test"


def main() -> int:
    common.cleanup_users("web-auth-")
    common.admin_emails(A)
    try:
        with common.client() as c:
            bad_email = c.post("/api/auth/request", json={"email": "메일아님"})
            outsider = c.post("/api/auth/request", json={"email": OUTSIDER})
            sent = c.post("/api/auth/request", json={"email": A})
            again = c.post("/api/auth/request", json={"email": A})
            link = common.last_link(A)
            no_session_me = c.get("/api/me")
            first = c.get(f"/auth/verify?token={link}", follow_redirects=False)
            session_cookie = c.cookies.get(auth.SESSION_COOKIE)
            me = c.get("/api/me")
            reused = c.get(f"/auth/verify?token={link}", follow_redirects=False)
            root_without_profile = c.get("/", follow_redirects=False)
            with db.session() as s:
                created = s.get(db.User, common.user_id(A))
            expired = c.get(f"/auth/verify?token={tokens.sign('login', {'email': A}, -1)}", follow_redirects=False)
            forged_token = tokens.sign("login", {"email": A}, 600)
            forged = c.get(f"/auth/verify?token={forged_token[:-3]}abc", follow_redirects=False)
            wrong_purpose = c.get(f"/auth/verify?token={tokens.sign('session', {'uid': 1}, 600)}", follow_redirects=False)
            c.cookies.clear()
            c.cookies.set(auth.SESSION_COOKIE, session_cookie[:-2] + "zz", domain="testserver.local", path="/")
            tampered_me = c.get("/api/me")
            c.cookies.clear()
            c.cookies.set(auth.SESSION_COOKIE, session_cookie, domain="testserver.local", path="/")
            restored_me = c.get("/api/me")
            logout = c.post("/api/auth/logout")
            after_logout = c.get("/api/me")
            mail_texts = [m["text"] for m in common.mails() if A in m["to"]]
    finally:
        removed = common.cleanup_users("web-auth-")
    checks = {
        "이메일_형식_틀리면_400": bad_email.status_code == 400,
        "개발모드_관리자_아닌_주소는_403": outsider.status_code == 403,
        "링크_메일_발송": sent.status_code == 200 and len(mail_texts) == 1 and "15분" in mail_texts[0],
        "1분_안_재요청은_429": again.status_code == 429,
        "세션없으면_API_401": no_session_me.status_code == 401,
        "첫_로그인은_설정으로·쿠키": first.status_code == 303 and first.headers["location"] == "/settings" and bool(session_cookie),
        "없던_사용자_생성·개발모드_is_test": created is not None and created.is_test is True and created.role == "",
        "세션으로_내정보": me.status_code == 200 and me.json()["email"] == A and me.json()["profile_done"] is False
        and me.json()["is_admin"] is True,
        "같은_링크_두번째는_거부": reused.headers["location"] == "/login?error=used",
        "프로필_없으면_오늘화면_대신_설정": root_without_profile.headers.get("location") == "/settings",
        "만료_링크_거부": expired.headers["location"] == "/login?error=expired",
        "위조_링크_거부": forged.headers["location"] == "/login?error=invalid"
        and wrong_purpose.headers["location"] == "/login?error=invalid",
        "변조_세션쿠키는_401": tampered_me.status_code == 401,
        "로그아웃하면_401": restored_me.status_code == 200 and logout.status_code == 200 and after_logout.status_code == 401,
        "검수용_사용자_정리": removed == 1,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
