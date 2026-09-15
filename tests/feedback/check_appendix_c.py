"""계획안 부록 C 검수 기준 3개 (피드백 루프). 모델은 가짜로 두고 가중치가 다음 날 정렬에 실제로 쓰이는지 본다.

실행: uv run python -m tests.feedback.check_appendix_c
1. 계정 A가 "가격·요금" 주제에 관심없음 3회 → 다음 날 그 주제 항목 순위가 계정 B보다 낮고, weights 값 -3이 트레이스(모델 입력·큐레이터 결과)에 보임
2. 계정 A가 노션 MCP에 써봤음 → 다음 관련 카드(F3-b) 후보에서 노션 계열 도구가 맨 위, 모델이 다른 순서로 골라도 카드 순서는 노션 먼저
3. 만료 링크 클릭 → 기록 0, "링크가 만료됐어요"
"""
import asyncio
import json
import re
import sys
from datetime import date

from tests.web import common

from langchain_core.messages import AIMessage  # noqa: E402
from sqlalchemy import delete, insert, select  # noqa: E402

import db  # noqa: E402
import memory  # noqa: E402
from agent import curator  # noqa: E402
from agent.structured import Stats  # noqa: E402
from pipeline import persist  # noqa: E402
from routes import tokens  # noqa: E402

A, B = "web-c-a@toolscout.test", "web-c-b@toolscout.test"
HOST = "https://example.test/appendix-c/"
DAY = date(2000, 1, 8)


def make_user(email: str) -> int:
    with db.get_engine().begin() as c:
        return c.execute(insert(db.User).values(email=email, role="개발자", is_test=True, profile_tools_tags=[],  # 태그 "notion"은 실제 도구 목록과도 겹쳐 순서 검수가 흔들린다
                                                notify_time="08:00", channel="email").returning(db.User.id)).scalar_one()


def seed(a_id: int) -> dict:
    specs = [("가격 소식 1", "news", "pricing"), ("가격 소식 2", "news", "pricing"), ("가격 소식 3", "news", "pricing"),
             ("노션 MCP", "mcp", "mcp_tools")]
    with db.get_engine().begin() as c:
        ids = {title: c.execute(insert(db.Item).values(date=DAY, type=k, topic=t, title=title, url=f"{HOST}{n}", source="test")
                                .returning(db.Item.id)).scalar_one() for n, (title, k, t) in enumerate(specs)}
        for rank, item_id in enumerate(ids.values(), 1):
            c.execute(insert(db.Briefing).values(user_id=a_id, date=DAY, item_id=item_id, rank=rank, trace_id="t",
                                                 card_json={"item_id": item_id, "type": "news", "title": "x"}))
    return ids


def cleanup() -> None:
    common.cleanup_users("web-c-")
    with db.get_engine().begin() as c:
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def fake_pick(prompts: list[str]):
    """모델 순서는 두 계정 모두 같게: 가격 뉴스를 먼저, 그다음 산업 뉴스."""
    def call(role, messages, tools=None):
        prompts.append(messages[-1].content)
        payload = json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S).group(1))
        order = sorted(payload["news"], key=lambda n: 0 if n["topic"] == "가격·요금·한도" else 1)
        return AIMessage(json.dumps({"news": [{"id": n["id"], "why": "검수"} for n in order], "tools": [], "empty_reason": None},
                                    ensure_ascii=False))
    return call


def main() -> int:
    cleanup()
    try:
        a_id, b_id = make_user(A), make_user(B)
        ids = seed(a_id)
        for title in ("가격 소식 1", "가격 소식 2", "가격 소식 3"):
            memory.apply_feedback(a_id, ids[title], "관심없음")
        tried = memory.apply_feedback(a_id, ids["노션 MCP"], "써봤음")
        mem_a, mem_b = memory.read(a_id), memory.read(b_id)
        selected = [{"title": "내일 가격 뉴스", "url": f"{HOST}tomorrow-pricing", "type": "news", "source": "openai", "topic": "pricing",
                     "reason": "검수", "summary": ""},
                    {"title": "내일 산업 뉴스", "url": f"{HOST}tomorrow-industry", "type": "news", "source": "openai", "topic": "industry",
                     "reason": "검수", "summary": ""}]
        prompts_a, prompts_b = [], []
        plan_a = asyncio.run(curator.pick_for_user(selected, mem_a, Stats(), fake_pick(prompts_a)))
        plan_b = asyncio.run(curator.pick_for_user(selected, mem_b, Stats(), fake_pick(prompts_b)))
        with db.get_engine().begin() as c:
            c.execute(insert(db.Item).values(date=DAY, type="mcp", topic="mcp_tools", title="노션 계열 MCP", url=f"{HOST}t1",
                                             description="노션 페이지 연동", source="mcp_registry", stars=1))
            c.execute(insert(db.Item).values(date=DAY, type="mcp", topic="coding_tools", title="다른 주제 도구", url=f"{HOST}t2",
                                             description="코드 검색", source="mcp_registry", stars=999999))
        pool = persist.related_pool(mem_a)
        pool_titles = [i["title"] for i in pool]

        def fake_related(role, messages, tools=None):  # 모델은 별 수 많은 다른 도구를 먼저 고른다
            payload = json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S).group(1))
            ids = {t["title"]: t["id"] for t in payload["tools"]}
            return AIMessage(json.dumps({"tools": [{"id": ids["다른 주제 도구"], "why": "검수"}, {"id": ids["노션 계열 MCP"], "why": "검수"}]},
                                        ensure_ascii=False))

        related = asyncio.run(curator.pick_related(pool, mem_a, set(), Stats(), fake_related))
        with common.client() as c:
            expired = c.post("/api/feedback/link", json={"token": tokens.sign("feedback", {"u": b_id, "i": ids["노션 MCP"], "a": "관심없음"}, -1)})
        with db.get_engine().connect() as conn:
            b_rows = conn.execute(select(db.Feedback.id).where(db.Feedback.user_id == b_id)).all()
    finally:
        cleanup()
    rank = lambda plan, title: next(i["rank"] for i in plan["news"] if i["title"] == title)  # noqa: E731
    checks = {
        "1_관심없음3회_weights_-3": mem_a["weights"].get("pricing") == -3,
        "1_다음날_그_주제_순위가_B보다_낮음": rank(plan_a, "내일 가격 뉴스") > rank(plan_b, "내일 가격 뉴스"),
        "1_weights_-3이_트레이스에_보임": '"가격·요금·한도": -3' in prompts_a[0] and plan_a["weights"].get("가격·요금·한도") == -3,
        "2_써봤음_주제_+1·써봤음_목록": tried["weight"] == 1 and f"{HOST}3" in mem_a["used_urls"],
        "2_다음_F3-b_후보에서_노션계열이_맨위": pool_titles[:1] == ["노션 계열 MCP"] and "다른 주제 도구" in pool_titles
        and pool[0]["match"] == ["노션"],
        "2_모델이_다른순서로_골라도_관련카드_노션먼저": [i["title"] for i in related] == ["노션 계열 MCP", "다른 주제 도구"],
        "3_만료_링크는_기록0·안내": expired.status_code == 400 and expired.json()["detail"] == "링크가 만료됐어요" and b_rows == [],
    }
    report = {"checks": checks, "ranks": {"A": [(i["title"], i["rank"]) for i in plan_a["news"]], "B": [(i["title"], i["rank"]) for i in plan_b["news"]]},
              "related_pool_top": pool_titles[:3], "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
