"""가입 승인과 공개 데모 검수 (2026-09-16 초대제, 2026-10-08 승인제·고정 예시 데모로 바뀜).

실행: uv run python -m tests.access.check_access
- 승인 전(pending) 사용자: 브리핑·검색·질문·피드백·프로필 API 403 7종, 화면은 /pending으로(승인 대기 화면 200),
  예전 초대 화면 주소 /invite도 /pending으로
- 관리자가 승인하면 같은 API가 통과하고, 승인된 사용자의 /pending은 홈으로
- 차단(blocked): 403, 하루 실행 대상(run_daily.target_user_ids)에서 pending·blocked·데모 프로필 제외
- 관리자(ADMIN_EMAILS)만 승인 대기 목록·상태 변경. 관리자가 아니면 403
- 공개 데모: 로그인 없이 /demo 200, /api/demo/briefing은 고정 예시(가상의 [예시] 카드·example.com 링크, DB의 실제 사용자 없음),
  피드백·질문 호출 없음, IP당 분당 60회 제한, /demo만 색인 허용(robots.txt·X-Robots-Tag)
검수용 사용자는 끝나면 지운다. 실제 메일은 보내지 않는다 (MAIL_FAKE_DIR).
"""
import json
import os
import sys
from datetime import date

from sqlalchemy import select

from tests.web import common

import db  # noqa: E402
from pipeline import run_daily  # noqa: E402
from routes import demo as demo_route  # noqa: E402

PENDING_EMAIL = "access-pending@toolscout.test"
ADMIN_EMAIL = "access-admin@toolscout.test"


def set_status(user_id: int, status: str) -> None:
    with db.session() as s:
        user = s.get(db.User, user_id)
        user.status = status
        s.commit()


def blocked_calls(c) -> dict[str, int]:
    """승인 전 사용자가 부르면 403이어야 하는 API 7종."""
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


def admin_checks(c, admin_c, pending_id: int) -> dict:
    """관리자 API. c는 관리자가 아닌 사용자(ADMIN_EMAILS에서 뺀 상태)."""
    not_admin = c.get("/api/admin/applications")
    queue = admin_c.get("/api/admin/applications").json()["applications"]
    in_queue = any(a["id"] == pending_id and a["via"] == "email" for a in queue)
    approved = admin_c.post(f"/api/admin/users/{pending_id}/status", json={"status": "approved"})
    after_approve = c.get("/api/briefings/today").status_code
    left_queue = all(a["id"] != pending_id for a in admin_c.get("/api/admin/applications").json()["applications"])
    blocked = admin_c.post(f"/api/admin/users/{pending_id}/status", json={"status": "blocked"})
    after_block = blocked_calls(c)
    restored = admin_c.post(f"/api/admin/users/{pending_id}/status", json={"status": "approved"})
    return {
        "관리자_아니면_403": not_admin.status_code == 403,
        "승인_대기_목록에_이메일_가입으로": in_queue,
        "관리자가_승인하면_브리핑_200": approved.status_code == 200 and after_approve == 200 and left_queue,
        "차단하면_403": blocked.status_code == 200 and set(after_block.values()) == {403},
        "되돌리면_다시_통과": restored.status_code == 200 and c.get("/api/briefings/today").status_code == 200,
    }


def demo_checks(c) -> dict:
    """로그인 없이 보는 고정 예시 화면. 실제 사용자 것이 새지 않는지 함께 본다."""
    demo_route._hits.clear()
    page = c.get("/demo")
    data = c.get("/api/demo/briefing")
    body = data.json()
    html = page.text
    text = json.dumps(body, ensure_ascii=False)
    with db.session() as s:
        real = s.exec(select(db.User).where(db.User.is_demo == False)).scalars().all()  # noqa: E712
    leaked = [u.email for u in real if u.email and u.email in text]
    leaked += [u.profile_free_text for u in real if u.profile_free_text and u.profile_free_text in text]
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
        "데모는_고정_예시": body["count"] == len(body["cards"]) >= 5 and all(card["title"].startswith("[예시]") for card in body["cards"])
        and all(card["url"].startswith("https://example.com/") for card in body["cards"]),
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
    """승인 전에는 승인 대기 화면만, 승인 뒤에는 원래 화면."""
    pending_home = c.get("/", follow_redirects=False)
    pending_settings = c.get("/settings", follow_redirects=False)
    pending_page = c.get("/pending", follow_redirects=False)
    old_invite = c.get("/invite", follow_redirects=False)
    approved_pending = approved_c.get("/pending", follow_redirects=False)
    return {
        "승인전_홈은_승인대기로": pending_home.status_code == 303 and pending_home.headers["location"] == "/pending",
        "승인전_설정도_승인대기로": pending_settings.status_code == 303 and pending_settings.headers["location"] == "/pending",
        "승인대기_화면_200": pending_page.status_code == 200,
        "예전_초대화면_주소는_승인대기로": old_invite.headers.get("location") == "/pending",
        "승인후_승인대기_화면은_홈으로": approved_pending.status_code == 303 and approved_pending.headers["location"] == "/",
    }


def daily_target_checks(user_id: int) -> dict:
    """하루 실행은 승인된 사용자만. 데모 프로필은 고정 예시라 뺀다 (2026-10-08)."""
    set_status(user_id, "pending")
    pending_targets = run_daily.target_user_ids()
    set_status(user_id, "blocked")
    blocked_targets = run_daily.target_user_ids()
    set_status(user_id, "approved")
    approved_targets = run_daily.target_user_ids()
    with db.get_engine().connect() as conn:
        demo_ids = [r[0] for r in conn.execute(select(db.User.id).where(db.User.is_demo == True))]  # noqa: E712
    return {
        "하루실행_pending_제외": user_id not in pending_targets,
        "하루실행_blocked_제외": user_id not in blocked_targets,
        "하루실행_approved_포함": user_id in approved_targets,
        "하루실행_데모_제외": not set(demo_ids) & set(approved_targets),
    }


def main() -> int:
    common.cleanup_users("access-")
    checks: dict = {}
    try:
        with common.client() as c:
            admin_c = common.second_client()
            common.login(admin_c, ADMIN_EMAIL)
            common.login(c, PENDING_EMAIL, approve=False)  # 승인 대기 상태 그대로
            pending_id = common.user_id(PENDING_EMAIL)
            me = c.get("/api/me").json()
            before = blocked_calls(c)
            checks["새_가입자는_pending"] = me["status"] == "pending" and me["approved"] is False
            checks["승인전_403_7종"] = len(before) == 7 and set(before.values()) == {403}
            checks.update(page_checks(c, admin_c))
            # 관리자 검사에서는 이 사용자를 관리자 목록에서 뺀다 (개발 모드 가입 때문에 넣어 뒀다)
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
        common.cleanup_users("access-")
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
