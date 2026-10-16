"""선별 판정 재사용 검수 (2026-10-16, agent/select_memo.py·curator.select known/judged). 모델은 가짜, DB는 실제(검수용 링크만 쓰고 지움).

실행: uv run python -m tests.agent.check_select_memo
- 오늘·어제 판정이 있는 뉴스는 모델에 보내지 않고, 그 판정이 통과면 선별에 그대로 들어간다(주제·중요도·근거 포함)
- 도구(MCP·스킬)는 판정이 있어도 매번 모델에 보낸다. 모델이 판정한 뉴스만 judged로 나온다
- 전부 재사용이면 모델을 부르지 않고 select_failed가 아니다
- DB: 저장 → 오늘·어제는 불러오고 그저께는 안 불러옴, 같은 날 다시 저장하면 덮어씀, 7일 지난 행은 지움
"""
import asyncio
import json
import random
import sys
from datetime import date, timedelta

from langchain_core.messages import AIMessage
from sqlmodel import col, delete

import db
from agent import curator, select_memo
from agent.structured import Stats

results: list[tuple[str, bool]] = []
TEST_URL = "https://check-select-memo.test/"


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("통과 " if ok else "실패 ") + name)


def fake(sent: list[str]):
    def call(role, messages, tools=None, **kw):
        system = messages[0].content
        if '"judgments"' in system:
            data = json.loads(messages[-1].content.split("<data>\n")[1].split("\n</data>")[0])
            sent.extend(d["title"] for d in data)
            reply = {"judgments": [{"id": d["id"], "ai_related": "통과" in d["title"], "worth_today": "통과" in d["title"], "topic": "industry",
                                    "importance": 3, "reason": "모델 판정"} for d in data]}
        elif '"groups"' in system:
            reply = {"groups": []}
        elif '"empty_reason"' in system:
            reply = {"news": [{"id": 1, "why": "고른 이유"}], "tools": [], "empty_reason": None}
        else:
            reply = {"requests": []}
        return AIMessage(json.dumps(reply, ensure_ascii=False), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    return call


def news(n: int, title: str) -> dict:
    return {"type": "news", "source": "aitimes", "title": title, "url": f"{TEST_URL}{n}", "summary": "s"}


async def selection() -> None:
    items = [news(1, "어제 통과"), news(2, "어제 탈락"), news(3, "새 통과"), news(4, "새 탈락"),
             {"type": "mcp", "source": "mcp_registry", "title": "도구 통과", "url": f"{TEST_URL}1", "summary": "s"}]
    known = {f"{TEST_URL}1": {"ai_related": True, "worth_today": True, "topic": "model_release", "importance": 5, "reason": "어제 근거"},
             f"{TEST_URL}2": {"ai_related": False, "worth_today": False, "topic": "industry", "importance": 2, "reason": "어제 근거"}}
    sent, judged = [], []
    selected = await curator.select(items, Stats(), random.Random(1), fake(sent), known, judged)
    by_title = {i["title"]: i for i in selected}
    check("판정_있는_뉴스는_모델에_안_보냄(도구는_보냄)", sorted(sent) == ["도구 통과", "새 탈락", "새 통과"])
    check("어제_통과는_그_판정으로_선별(주제·중요도·근거)", by_title.get("어제 통과", {}).get("topic") == "model_release"
          and by_title["어제 통과"]["importance"] == 5 and by_title["어제 통과"]["reason"] == "어제 근거")
    check("어제_탈락은_선별에_없음", "어제 탈락" not in by_title)
    check("새_뉴스·도구는_모델_판정대로", "새 통과" in by_title and "새 탈락" not in by_title and "도구 통과" in by_title)
    check("judged는_모델이_판정한_뉴스만", sorted(j["title"] for j in judged) == ["새 탈락", "새 통과"]
          and all(set(j) == {"url", "title", "ai_related", "worth_today", "topic", "importance", "reason"} for j in judged))
    mem = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": []}
    sent2 = []
    result = await curator.run(items[:2], [mem], seed=1, model_call=fake(sent2), known=known)
    check("전부_재사용이면_모델_안_부르고_select_failed_아님", not [s for s in sent2 if s in ("어제 통과", "어제 탈락")]
          and not result["select_failed"] and [i["title"] for i in result["selected"]] == ["어제 통과"] and result["judged"] == [])


def storage() -> None:
    today = date(2026, 10, 16)
    with db.session() as s:
        s.exec(delete(db.SelectMemo).where(col(db.SelectMemo.url).startswith(TEST_URL)))
        s.commit()
    row = {"ai_related": True, "worth_today": True, "topic": "industry", "importance": 3, "reason": "근거"}
    select_memo.save(today - timedelta(days=2), [row | {"url": f"{TEST_URL}a", "title": "그저께"}])
    select_memo.save(today - timedelta(days=1), [row | {"url": f"{TEST_URL}b", "title": "어제"}])
    saved = select_memo.save(today, [row | {"url": f"{TEST_URL}c", "title": "오늘", "worth_today": False}, row | {"url": "", "title": "링크 없음"}])
    select_memo.save(today, [row | {"url": f"{TEST_URL}c", "title": "오늘 다시"}])
    items = [news(n, n) for n in ("a", "b", "c")] + [{"type": "mcp", "url": f"{TEST_URL}b"}]
    loaded = select_memo.load(today, items)
    check("링크_없는_판정은_저장_안함", saved == 1)
    check("오늘·어제는_불러오고_그저께는_안_불러옴", sorted(loaded) == [f"{TEST_URL}b", f"{TEST_URL}c"])
    check("같은_날_다시_저장하면_덮어씀", loaded[f"{TEST_URL}c"]["worth_today"] is True)
    select_memo.save(today + timedelta(days=9), [])
    check("7일_지난_행은_지움", select_memo.load(today - timedelta(days=1), items) == {})
    with db.session() as s:
        s.exec(delete(db.SelectMemo).where(col(db.SelectMemo.url).startswith(TEST_URL)))
        s.commit()


def main() -> int:
    db.init_db()  # select_memos 표가 없으면 만든다(다른 검수와 같은 방식, 운영 DB에도 생긴다)
    asyncio.run(selection())
    storage()
    passed = sum(ok for _, ok in results)
    print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
