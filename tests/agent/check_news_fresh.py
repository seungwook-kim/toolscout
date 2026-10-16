"""뉴스 새로움 검수 (2026-10-16 사용자 "일반 AI보다 더 빠른 뉴스"). 모델은 가짜.

실행: uv run python -m tests.agent.check_news_fresh
- 사용자 뉴스는 원문이 fresh_since(실행 시각 - 26시간) 뒤인 것만 후보가 되고, 뺀 수는 excluded.stale에 남는다
- 원문 시각을 모르는 뉴스와 도구는 거르지 않는다. fresh_since가 없으면(검수 가짜 실행) 거르지 않는다
- 큰 소식은 묶음 기사가 모두 오래됐으면 올리지 않고, 하나라도 새것이면 올린다(다룬 곳은 오래된 기사까지 센다). 묶인 기사 제목이 남는다
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

from agent import curator, headline
from agent.structured import Stats

NOW = datetime(2026, 10, 16, 22, 0, tzinfo=timezone.utc)
SINCE = NOW - curator.FRESH_NEWS
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("통과 " if ok else "실패 ") + name)


def ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).isoformat(timespec="seconds")


def news(n: int, title: str, hours: float | None, source: str = "aitimes") -> dict:
    return {"type": "news", "source": source, "title": title, "url": f"https://fresh.test/{n}", "topic": "industry",
            "importance": 5, "reason": "판정", "summary": "s", "published_at": ago(hours) if hours is not None else None}


def usage(text: str) -> AIMessage:
    return AIMessage(text, usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


def fake(role, messages, tools=None, **kw):
    """후보 단계는 뉴스·도구를 모두 고르고, 묶기는 제목 앞 글자가 같은 것끼리 묶는다."""
    data = json.loads(messages[-1].content.split("<data>\n")[1].split("\n</data>")[0])
    if isinstance(data, dict):
        return usage(json.dumps({"news": [{"id": d["id"], "why": "골랐습니다"} for d in data["news"]],
                                 "tools": [{"id": d["id"], "why": "골랐습니다"} for d in data["tools"]], "empty_reason": None}))
    by_head: dict[str, list[int]] = {}
    for d in data:
        by_head.setdefault(d["title"][0], []).append(d["id"])
    return usage(json.dumps({"groups": [g for g in by_head.values() if len(g) > 1]}))


MEMORY = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": [], "seen_recent_urls": []}


async def user_news() -> None:
    selected = [news(1, "새 소식", 3), news(2, "어제 소식", 30), news(3, "시각 모름", None),
                {"type": "mcp", "source": "mcp_registry", "title": "옛 도구", "url": "https://fresh.test/t", "topic": "mcp_tools",
                 "summary": "s", "published_at": ago(100), "stars": 1}]
    plan = await curator.pick_for_user(selected, MEMORY, Stats(), fake, SINCE)
    titles = [i["title"] for i in plan["news"]]
    check("26시간_지난_뉴스는_사용자_후보에서_빠짐", "어제 소식" not in titles and "새 소식" in titles)
    check("원문_시각_모르는_뉴스는_거르지_않음", "시각 모름" in titles)
    check("도구는_원문_시각으로_거르지_않음", [i["title"] for i in plan["tools"]] == ["옛 도구"])
    check("뺀_수는_excluded_stale", plan["excluded"]["stale"] == 1)
    plain = await curator.pick_for_user(selected, MEMORY, Stats(), fake)
    check("fresh_since_없으면_거르지_않음", len(plain["news"]) == 3 and plain["excluded"]["stale"] == 0)


async def headlines() -> None:
    old = [news(10 + n, f"가 옛 소식 {n}", 40 + n, s) for n, s in enumerate(("aitimes", "techcrunch_ai", "geeknews"))]
    mixed = [news(20, "나 오늘 소식", 2, "geeknews")] + [news(21 + n, f"나 오늘 소식 {n}", 35, s)
                                                       for n, s in enumerate(("aitimes", "techcrunch_ai"))]
    tops = await headline.pick(old + mixed, Stats(), fake, SINCE)
    check("묶음_기사가_모두_오래되면_큰_소식_아님", all(not t["title"].startswith("가") for t in tops))
    check("하나라도_새것이면_큰_소식_다룬_곳은_오래된_기사까지", [(t["title"][0], t["coverage"]) for t in tops] == [("나", 3)])
    check("묶인_기사_제목이_남음", len(tops) == 1 and len(tops[0]["group_titles"]) == 3)
    unfiltered = await headline.pick(old + mixed, Stats(), fake)
    check("fresh_since_없으면_오래된_묶음도_큰_소식", "가" in [t["title"][0] for t in unfiltered])


def main() -> int:
    asyncio.run(user_news())
    asyncio.run(headlines())
    passed = sum(ok for _, ok in results)
    print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
