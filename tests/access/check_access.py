"""초대제 가입과 공개 데모 검수 (2026-09-16 사용자 요청 3번).

실행: uv run python -m tests.access.check_access
- 승인 전(pending) 사용자: 브리핑·검색·질문·피드백·프로필 API 403 6종, 화면은 /invite로
- 초대 코드: 없는 코드·기한 지난 코드·다 쓴 코드 거부, 맞으면 승인 → 같은 API가 통과, 코드 used +1
- 차단(blocked): 403, 하루 실행 대상(run_daily.target_user_ids)에서 pending·blocked 제외
- 관리자(ADMIN_EMAILS): 코드 생성·목록·상태 변경. 관리자가 아니면 403
- 공개 데모: 로그인 없이 /demo 200, /api/demo/briefing 200, 실제 사용자 프로필·카드 없음, 피드백·질문 호출 없음,
  IP당 분당 60회 제한, /demo만 색인 허용(robots.txt·X-Robots-Tag)
검수용 사용자와 코드는 끝나면 지운다. 실제 메일은 보내지 않는다 (MAIL_FAKE_DIR).
"""
import json
import os
import sys
from datetime import date, timedelta

from sqlalchemy import delete, select

from tests.web import common

import db  # noqa: E402
from pipeline import run_daily  # noqa: E402
from routes import demo as demo_route  # noqa: E402

PENDING_EMAIL = "access-pending@toolscout.test"
ADMIN_EMAIL = "access-admin@toolscout.test"
CODES = {"ok": "ACCESSOK", "expired": "ACCESSEX", "used_up": "ACCESSUP"}


def seed_codes() -> None:
    drop_codes()
    with db.session() as s:
        s.add(db.InviteCode(code=CODES["ok"], max_uses=2, expires_at=db.utcnow() + timedelta(days=1)))
        s.add(db.InviteCode(code=CODES["expired"], max_uses=5, expires_at=db.utcnow() - timedelta(days=1)))
        s.add(db.InviteCode(code=CODES["used_up"], max_uses=1, used=1, expires_at=None))
        s.commit()


def drop_codes() -> None:
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.InviteCode).where(db.InviteCode.code.like("ACCESS%")))


def code_used(code: str) -> int:
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.InviteCode.used).where(db.InviteCode.code == code)).scalar() or 0


def set_status(user_id: int, status: str) -> None:
    with db.session() as s:
        user = s.get(db.User, user_id)
        user.status = status
        s.commit()


def blocked_calls(c) -> dict[str, int]:
    """승인 전 사용자가 부르면 403이어야 하는 API 6종."""
    today = str(date.today())
    return {
        "오늘_브리핑": c.get("/api/briefings/today").status_code,
        "날짜_브리핑": c.get(f"/api/briefings?date={today}").status_code,
        "날짜_목록": c.get("/api/briefings/dates").status_code,
        "검색": c.get("/api/search?q=에이전트").status_code,
        "질문": c.post("/api/ask", json={"question": "오늘 뭐 있어?"}).status_code,
        "피드백": c.post("/api/feedback", json={"item_id": 1, "action": "관심없음"}).status_code,
        "프로필": c.get("/api/profile").status_code,
    }


def invite_checks(c, user_id: int) -> dict:
    wrong = c.post("/api/invite/redeem", json={"code": "NOPECODE"})
    expired = c.post("/api/invite/redeem", json={"code": CODES["expired"]})
    used_up = c.post("/api/invite/redeem", json={"code": CODES["used_up"]})
    before = code_used(CODES["ok"])
    ok = c.post("/api/invite/redeem", json={"code": CODES["ok"].lower()})  # 소문자로 넣어도 된다
    after_status = c.get("/api/me").json()
    return {
        "없는_코드_거부": wrong.status_code == 400,
        "기한_지난_코드_거부": expired.status_code == 400 and "기한" in expired.json()["detail"],
        "다_쓴_코드_거부": used_up.status_code == 400 and "다 쓴" in used_up.json()["detail"],
        "맞는_코드는_승인": ok.status_code == 200 and after_status["status"] == "approved" and after_status["approved"] is True,
        "코드_사용수_증가": code_used(CODES["ok"]) == before + 1,
        "코드_기록": _invite_code_of(user_id) == CODES["ok"],
    }


def _invite_code_of(user_id: int) -> str | None:
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.User.invite_code_used).where(db.User.id == user_id)).scalar()


def admin_checks(c, admin_c, pending_id: int) -> dict:
    """관리자 API. c는 관리자가 아닌 사용자(ADMIN_EMAILS에서 뺀 상태)."""
    not_admin = c.get("/api/admin/invites")
    created = admin_c.post("/api/admin/invites", json={"max_uses": 3, "expires_days": 7})
    listed = admin_c.get("/api/admin/invites").json()
    new_code = created.json().get("code", "")
    blocked = admin_c.post(f"/api/admin/users/{pending_id}/status", json={"status": "blocked"})
    after_block = blocked_calls(c)
    restored = admin_c.post(f"/api/admin/users/{pending_id}/status", json={"status": "approved"})
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.InviteCode).where(db.InviteCode.code == new_code))
    return {
        "관리자_아니면_403": not_admin.status_code == 403,
        "코드_생성": created.status_code == 200 and len(new_code) == 8,
        "코드_목록에_남음": any(row["code"] == new_code and row["max_uses"] == 3 for row in listed["codes"]),
        "차단하면_403": blocked.status_code == 200 and set(after_block.values()) == {403},
        "되돌리면_다시_통과": restored.status_code == 200 and c.get("/api/briefings/today").status_code == 200,
    }


def demo_checks(c) -> dict:
    """로그인 없이 보는 화면. 실제 사용자 것이 새지 않는지 함께 본다."""
    demo_route._hits.clear()
    page = c.get("/demo")
    data = c.get("/api/demo/briefing")
    body = data.json()
    html = page.text
    with db.session() as s:
        real = s.exec(select(db.User).where(db.User.is_demo == False, db.User.is_test == True)).scalars().all()  # noqa: E712
    leaked = [u.email for u in real if u.email and u.email in json.dumps(body, ensure_ascii=False)]
    free_texts = [u.profile_free_text for u in real if u.profile_free_text]
    leaked += [t for t in free_texts if t in json.dumps(body, ensure_ascii=False)]
    session_needed = c.get("/api/briefings/today")
    demo_route._hits.clear()
    for _ in range(demo_route.RATE_LIMIT):
        c.get("/demo")
    limited = c.get("/demo")
    demo_route._hits.clear()
    robots = c.get("/robots.txt")
    return {
        "로그인_없이_데모_200": page.status_code == 200 and data.status_code == 200 and body["demo"] is True,
        "데모_안내_문구": demo_route.NOTICE in body["notice"],
        "데모에_버튼·질문_없음": "/api/ask" not in html and "data-action" not in html and "Cards.readonly = true" in html,
        "데모_카드에_피드백·트레이스_없음": all(not card["feedback"]["actions"] and "trace_url" not in card for card in body["cards"])
        and "is_admin" not in body,
        "실제_사용자_노출_없음": not leaked,
        "데모_말고는_세션_필요": session_needed.status_code == 401,
        "분당_60회_제한": limited.status_code == 429,
        "색인은_데모만": "Allow: /demo" in robots.text and "Disallow: /" in robots.text
        and c.get("/login").headers.get("x-robots-tag") == "noindex" and "x-robots-tag" not in {k.lower() for k in page.headers},
    }


def page_checks(c, approved_c) -> dict:
    """승인 전에는 초대 화면만, 승인 뒤에는 원래 화면."""
    pending_home = c.get("/", follow_redirects=False)
    pending_settings = c.get("/settings", follow_redirects=False)
    pending_invite = c.get("/invite", follow_redirects=False)
    approved_invite = approved_c.get("/invite", follow_redirects=False)
    return {
        "승인전_홈은_초대화면으로": pending_home.status_code == 303 and pending_home.headers["location"] == "/invite",
        "승인전_설정도_초대화면으로": pending_settings.status_code == 303 and pending_settings.headers["location"] == "/invite",
        "승인전_초대화면_200": pending_invite.status_code == 200,
        "승인후_초대화면은_홈으로": approved_invite.status_code == 303 and approved_invite.headers["location"] == "/",
    }


def daily_target_checks(user_id: int) -> dict:
    """하루 실행은 승인된 사용자만 (데모 프로필은 들어간다)."""
    set_status(user_id, "pending")
    pending_targets = run_daily.target_user_ids()
    set_status(user_id, "blocked")
    blocked_targets = run_daily.target_user_ids()
    set_status(user_id, "approved")
    approved_targets = run_daily.target_user_ids()
    with db.get_engine().connect() as conn:
        demo_id = conn.execute(select(db.User.id).where(db.User.is_demo == True)).scalar()  # noqa: E712
    return {
        "하루실행_pending_제외": user_id not in pending_targets,
        "하루실행_blocked_제외": user_id not in blocked_targets,
        "하루실행_approved_포함": user_id in approved_targets,
        "하루실행_데모_포함": demo_id in approved_targets,
    }


def main() -> int:
    common.cleanup_users("access-")
    seed_codes()
    checks: dict = {}
    try:
        with common.client() as c:
            admin_c = common.second_client()
            common.login(admin_c, ADMIN_EMAIL)
            common.login(c, PENDING_EMAIL, approve=False)  # 초대 대기 상태 그대로
            pending_id = common.user_id(PENDING_EMAIL)
            admin_id = common.user_id(ADMIN_EMAIL)
            set_status(admin_id, "approved")
            me = c.get("/api/me").json()
            before = blocked_calls(c)
            checks["새_가입자는_pending"] = me["status"] == "pending" and me["approved"] is False
            checks["승인전_403_6종"] = len(before) >= 6 and set(before.values()) == {403}
            checks.update(page_checks(c, admin_c))
            checks.update(invite_checks(c, pending_id))
            checks["승인후_브리핑_200"] = c.get("/api/briefings/today").status_code == 200
            # 관리자 검사에서는 이 사용자를 관리자 목록에서 뺀다 (개발 모드 로그인 때문에 넣어 뒀다)
            saved = os.environ.get("ADMIN_EMAILS", "")
            os.environ["ADMIN_EMAILS"] = ",".join(e for e in saved.split(",") if e.strip() != PENDING_EMAIL)
            try:
                checks.update(admin_checks(c, admin_c, pending_id))
            finally:
                os.environ["ADMIN_EMAILS"] = saved
            checks.update(daily_target_checks(pending_id))
            c.post("/api/auth/logout")
            c.cookies.clear()
            checks.update(demo_checks(c))
    finally:
        drop_codes()
        common.cleanup_users("access-")
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
