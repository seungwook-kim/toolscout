"""뉴스 선별 규칙 검수 (2026-10-16 사용자 결정 "B로 가자": 뉴스는 AI 관련이면 후보, 별점(중요도) 순으로 나온다). 모델은 가짜.

실행: uv run python -m tests.agent.check_select_rule
- 뉴스는 ai_related면 worth_today가 false여도 선별에 들어가고, AI 무관 뉴스는 빠진다
- 도구(MCP·스킬)는 전처럼 ai_related이고 worth_today여야 들어간다
- 재사용 판정(select_memo)도 같은 규칙
- 사용자 후보 단계 입력은 별점(중요도) 높은 순, 같은 별점이면 주제 가중치 순, 후보 모델에게 별점을 보여 준다
- 뉴스는 큰 소식 포함 최대 10건, 별점 3 이상만, 별점 높은 순 (2026-10-16 사용자 "점수 높은 순위로 뉴스 10개")
"""
import asyncio
import json
import random
import sys

from langchain_core.messages import AIMessage

from agent import curator, headline
from agent.structured import Stats

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("통과 " if ok else "실패 ") + name)


def fake(role, messages, tools=None, **kw):
    data = json.loads(messages[-1].content.split("<data>\n")[1].split("\n</data>")[0])
    return AIMessage(json.dumps({"judgments": [{"id": d["id"], "ai_related": "무관" not in d["title"], "worth_today": "볼만" in d["title"],
                                                "topic": "industry", "importance": 3, "reason": "판정"} for d in data]}, ensure_ascii=False),
                     usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


def item(n: int, title: str, kind: str = "news") -> dict:
    return {"type": kind, "source": "aitimes", "title": title, "url": f"https://rule.test/{n}", "summary": "s"}


async def selection() -> None:
    items = [item(1, "AI 인터뷰"), item(2, "AI 볼만 출시"), item(3, "무관 소식"), item(4, "도구", "mcp"), item(5, "도구 볼만", "mcp")]
    known = {"https://rule.test/9": {"ai_related": True, "worth_today": False, "topic": "industry", "importance": 4, "reason": "어제"}}
    selected = await curator.select(items + [item(9, "어제 본 AI 논평")], Stats(), random.Random(1), fake, known, [])
    titles = sorted(i["title"] for i in selected)
    check("뉴스는_AI_관련이면_worth_today_false여도_후보", "AI 인터뷰" in titles and "AI 볼만 출시" in titles)
    check("AI_무관_뉴스는_빠짐", "무관 소식" not in titles)
    check("도구는_AI_관련이고_볼_만해야_후보", "도구 볼만" in titles and "도구" not in titles)
    check("재사용_판정도_같은_규칙(AI_관련_뉴스는_후보)", "어제 본 AI 논평" in titles)


def ranking() -> None:
    news = [{"type": "news", "title": f"n{s}", "topic": "industry", "source": "aitimes", "importance": s} for s in (3, 5, 2, 4)]
    news.append({"type": "news", "title": "가중치", "topic": "model_release", "source": "aitimes", "importance": 3})
    pool, _ = curator._pick_pool(news, [], {"model_release": 2})
    check("후보_입력은_별점_다음_가중치_순·별점_2_이하_뺌", [i["title"] for i in pool] == ["n5", "n4", "가중치", "n3"])
    check("후보_프롬프트에_별점_높은_뉴스_먼저_최대_10건", "별점이 높을수록 먼저" in curator.PICK_PROMPT and "최대 10건" in curator.PICK_PROMPT)
    check("선별_프롬프트에_뉴스는_ai_related만", "뉴스(type news)는 ai_related만으로 후보가 된다" in curator.SELECT_PROMPT)


def pick_fake(role, messages, tools=None, **kw):
    """후보 단계는 뉴스를 거꾸로(별점 낮은 것부터) 모두 고른다. 같은 소식 묶기는 묶을 것 없음."""
    data = json.loads(messages[-1].content.split("<data>\n")[1].split("\n</data>")[0])
    if isinstance(data, list):
        return AIMessage('{"groups": []}', usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    picks = [{"id": d["id"], "why": "골랐습니다"} for d in reversed(data["news"])][:curator.schemas.MAX_NEWS]
    return AIMessage(json.dumps({"news": picks, "tools": [], "empty_reason": None}),
                     usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


async def ten_news() -> None:
    stars = [5, 5, 4, 4, 4, 3, 3, 3, 3, 3, 3, 2, 2, 1]
    news = [{**item(20 + n, f"m{n}"), "topic": "industry", "importance": s, "reason": "r"} for n, s in enumerate(stars)]
    memory = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": [], "seen_recent_urls": []}
    plan = await curator.pick_for_user(news, memory, Stats(), pick_fake)
    got = [i["importance"] for i in plan["news"]]
    check("뉴스는_최대_10건(MAX_NEWS)", curator.schemas.MAX_NEWS == 10 and len(got) == 10)
    check("별점_2_이하는_보여_주지_않음", min(got) >= curator.MIN_IMPORTANCE == 3)
    check("모델이_순서를_바꿔도_별점_높은_순", got == sorted(got, reverse=True) and [i["rank"] for i in plan["news"]] == list(range(1, 11)))
    top = {**item(99, "큰 소식"), "importance": 5, "headline": True, "group_urls": ["https://rule.test/99"]}
    out = headline.attach(plan, [top], memory)
    titles = [i["title"] for i in out["news"]]
    check("큰_소식_포함_10건·큰_소식이_맨_위", len(titles) == 10 and titles[0] == "큰 소식"
          and [i["importance"] for i in out["news"][1:]] == sorted([i["importance"] for i in out["news"][1:]], reverse=True))


def main() -> int:
    asyncio.run(selection())
    ranking()
    asyncio.run(ten_news())
    passed = sum(ok for _, ok in results)
    print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
