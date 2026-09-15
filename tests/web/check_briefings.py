"""오늘 브리핑·지난 브리핑·검색 API 검수. 검수용 사용자 2명과 항목을 넣고 끝나면 지운다 (모델 호출 없음).

실행: uv run python -m tests.web.check_briefings
"""
import json
import os
import sys
from datetime import timedelta

from tests.web import common

from sqlalchemy import delete, insert, select  # noqa: E402

import db  # noqa: E402
from pipeline.run_daily import today_kst  # noqa: E402

A, B = "web-brief-a@toolscout.test", "web-brief-b@toolscout.test"
HOST = "https://example.test/web-brief/"


def card(n: int, kind: str, item_id: int) -> dict:
    return {"item_id": item_id, "type": kind, "title": f"검수 카드 {n}", "url": f"{HOST}{n}", "summary_ko": f"요약 {n}",
            "for_me": f"나한테는 {n}", "why_this_card": f"이유 {n}", "source_checked": True, "notice": None, "relevance": 4,
            "pros": [{"text": "좋은 점", "evidence_url": f"{HOST}{n}"}], "cons": [], "install_cmd": "npx -y x" if kind == "mcp" else None,
            "trace_id": f"trace-{n}", "rank": n}


def seed(a_id: int, b_id: int) -> dict:
    today, yesterday = today_kst(), today_kst() - timedelta(days=1)
    with db.get_engine().begin() as c:
        ids = [c.execute(insert(db.Item).values(date=today, type=k, topic=t, title=f"검수 카드 {n}", url=f"{HOST}{n}",
                                                summary_ko=f"요약 {n} 노션 연동", source="test").returning(db.Item.id)).scalar_one()
               for n, k, t in ((1, "news", "pricing"), (2, "mcp", "mcp_tools"), (3, "news", "industry"))]
        for rank, (n, kind) in enumerate(((1, "news"), (2, "mcp")), 1):
            c.execute(insert(db.Briefing).values(user_id=a_id, date=today, item_id=ids[n - 1], rank=rank, card_json=card(n, kind, ids[n - 1]),
                                                 trace_id=f"trace-{n}", pool_size=120))
        c.execute(insert(db.Briefing).values(user_id=a_id, date=yesterday, item_id=None, rank=0, card_json=None,
                                             empty_reason="어제는 볼 만한 게 없었다", trace_id="trace-empty", pool_size=90))
        c.execute(insert(db.Briefing).values(user_id=b_id, date=today, item_id=ids[2], rank=1, card_json=card(3, "news", ids[2]),
                                             trace_id="trace-3", pool_size=120))
        c.execute(insert(db.Feedback).values(user_id=a_id, item_id=ids[0], action="관심없음", created_at=db.utcnow()))
    return {"items": ids, "today": today, "yesterday": yesterday}


def cleanup() -> None:
    with db.get_engine().begin() as c:
        ids = [r[0] for r in c.execute(select(db.Item.id).where(db.Item.url.like(f"{HOST}%")))]
        common.cleanup_users("web-brief-")
        c.execute(delete(db.Item).where(db.Item.id.in_(ids)))


def profile(c, role: str) -> None:
    c.post("/api/profile", json={"role": role, "tools_tags": ["python"], "free_text": "검수용 한 줄", "weights": {}})


def main() -> int:
    cleanup()
    try:
        cb = common.second_client()
        with common.client() as ca:
            no_session = ca.get("/api/briefings/today")
            common.login(ca, A)
            common.login(cb, B)
            profile(ca, "개발자")
            profile(cb, "마케터")
            data = seed(common.user_id(A), common.user_id(B))
            common.admin_emails(A)
            os.environ["ADMIN_EMAILS"] = ",".join(e for e in os.environ["ADMIN_EMAILS"].split(",") if e != B)  # B는 관리자 아님
            today_a = ca.get("/api/briefings/today").json()
            today_b = cb.get("/api/briefings/today").json()
            past_a = ca.get(f"/api/briefings?date={data['yesterday']}").json()
            dates_a = ca.get("/api/briefings/dates").json()
            search_a = ca.get("/api/search?q=노션").json()
            search_b = cb.get("/api/search?q=노션").json()
            short = ca.get("/api/search?q=a")
            page = ca.get("/")
    finally:
        cleanup()
    cards = {c["title"]: c for c in today_a["cards"]}
    checks = {
        "세션없으면_401": no_session.status_code == 401,
        "오늘_내_카드만·순위": [c["title"] for c in today_a["cards"]] == ["검수 카드 1", "검수 카드 2"]
        and [c["title"] for c in today_b["cards"]] == ["검수 카드 3"],
        "N건_중_M건·기준_한줄": today_a["pool_size"] == 120 and today_a["count"] == 2 and today_a["profile_line"] == "개발자 · python · 검수용 한 줄",
        "내_피드백_상태_표시": cards["검수 카드 1"]["feedback"]["actions"] == ["관심없음"] and cards["검수 카드 2"]["feedback"]["actions"] == [],
        "주제_이름_붙음": cards["검수 카드 1"]["topic_label"] == "가격·요금·한도",
        "관리자만_트레이스_주소": all("trace_url" in c for c in today_a["cards"]) and all("trace_url" not in c for c in today_b["cards"]),
        "카드0건_날은_empty_reason": past_a["count"] == 0 and past_a["empty_reason"] == "어제는 볼 만한 게 없었다" and past_a["exists"],
        "날짜_목록_최신순": [d["date"] for d in dates_a["dates"]] == [str(data["today"]), str(data["yesterday"])]
        and dates_a["dates"][0]["cards"] == 2,
        "검색은_내_브리핑_항목만": {r["title"] for r in search_a["results"]} == {"검수 카드 1", "검수 카드 2"}
        and {r["title"] for r in search_b["results"]} == {"검수 카드 3"},
        "검색어_짧으면_400": short.status_code == 400,
        "오늘_화면_열림": page.status_code == 200 and "cards.js" in page.text,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
