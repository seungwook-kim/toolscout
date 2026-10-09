"""프로필·설정 검수. 앱을 프로세스 안에서 띄우고, "지금 만들기"는 가짜 실행으로 바꾼다 (모델 호출 없음).

실행: uv run python -m tests.web.check_settings
"""
import json
import sys

from tests.web import common

import db  # noqa: E402
from sqlalchemy import insert, select  # noqa: E402

A = "web-set-a@toolscout.test"


def main() -> int:
    common.cleanup_users("web-set-")
    calls = []
    try:
        with common.client() as c:
            from routes import settings

            async def fake_run_now(users=None, limit=None, user_ids=None):
                calls.append(user_ids)
                return {"status": "done", "date": "2000-01-01", "totals": {"cards": 1}}

            settings.scheduler.run_now = fake_run_now
            no_session = c.get("/api/profile")
            common.login(c, A)
            uid = common.user_id(A)
            before = c.get("/api/profile").json()
            first = {path: c.get(path, follow_redirects=False) for path in ("/", "/history", "/settings", "/onboarding")}
            now_without_profile = c.post("/api/briefing/now")
            bad_role = c.post("/api/profile", json={"role": "우주비행사"})
            weights = dict(before["presets"]["개발자"]) | {"pricing": -9, "mcp_tools": 9}
            saved = c.post("/api/profile", json={"role": "개발자", "tools_tags": ["python", " ", "claude code", "python"],
                                                 "free_text": "AI 에이전트를 공부한다", "weights": weights, "notify_time": "09:00"})
            after = c.get("/api/profile").json()
            long_texts = {}  # 자유 한 줄은 200자까지 (2026-10-09 사용자 결정): 200자는 그대로, 250자는 200자로 잘림
            for n in (200, 250):
                c.post("/api/profile", json={"role": "개발자", "tools_tags": ["python", "claude code"], "free_text": "가" * n,
                                             "weights": weights, "notify_time": "09:00"})
                long_texts[n] = c.get("/api/profile").json()["profile"]["free_text"]
            root = c.get("/", follow_redirects=False)
            onboarding_after = c.get("/onboarding", follow_redirects=False)
            settings_after = c.get("/settings", follow_redirects=False)
            now = c.post("/api/briefing/now")
            status = c.get("/api/briefing/now").json()
            with db.get_engine().begin() as conn:  # 기억 지우기 대상 행을 하나씩 만든다
                item_id = conn.execute(select(db.Item.id).limit(1)).scalar_one()
                conn.execute(insert(db.Seen).values(user_id=uid, item_id=item_id, shown_at=db.utcnow()))
                conn.execute(insert(db.Feedback).values(user_id=uid, item_id=item_id, action="관심없음", created_at=db.utcnow()))
            forgot = c.post("/api/memory/forget").json()
            after_forget = c.get("/api/profile").json()
            deleted = c.post("/api/account/delete")
            after_delete = c.get("/api/me")
            gone = common.user_id(A) is None
    finally:
        common.cleanup_users("web-set-")
    checks = {
        "세션없으면_401": no_session.status_code == 401,
        "첫_설정은_first_time·직군5·주제10": before["first_time"] is True and before["roles"] == ["개발자", "기획자", "마케터", "학생", "기타"]
        and len(before["topics"]) == 10 and set(before["presets"]) == set(before["roles"]),
        "프로필_없이_지금만들기_거부": now_without_profile.status_code == 400,
        "없는_직군은_400": bad_role.status_code == 400,
        "저장_직군·도구정리·알림시간": saved.status_code == 200 and after["profile"]["role"] == "개발자"
        and after["profile"]["tools_tags"] == ["python", "claude code"] and after["profile"]["notify_time"] == "09:00",
        "자유_한줄_200자까지": long_texts[200] == "가" * 200 and long_texts[250] == "가" * 200,
        "가중치_초기값_반영·-5~+5_고정": after["profile"]["weights"]["pricing"] == -5 and after["profile"]["weights"]["mcp_tools"] == 5
        and after["profile"]["has_weights"] is True,
        "프로필_저장후_오늘화면_열림": root.status_code == 200,
        "프로필_비면_오늘·지난·설정은_첫설정으로": all(first[p].status_code == 303 and first[p].headers["location"] == "/onboarding" for p in ("/", "/history", "/settings"))
        and first["/onboarding"].status_code == 200,
        "프로필_차면_첫설정은_오늘로·설정_열림": onboarding_after.headers["location"] == "/" and settings_after.status_code == 200,
        "지금만들기_본인만_실행": now.status_code == 202 and calls == [[uid]] and status["status"] in ("running", "done"),
        "기억지우기_weights·seen·feedback_삭제": forgot["deleted"]["weights"] == 10 and forgot["deleted"]["seen"] == 1
        and forgot["deleted"]["feedback"] == 1 and after_forget["profile"]["has_weights"] is False,
        "계정삭제_사용자·세션_끝": deleted.status_code == 200 and after_delete.status_code == 401 and gone,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
