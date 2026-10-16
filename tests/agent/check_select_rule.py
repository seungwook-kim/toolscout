"""뉴스 선별 규칙 검수 (2026-10-16 사용자 결정 "B로 가자": 뉴스는 AI 관련이면 후보, 별점(중요도) 순으로 나온다). 모델은 가짜.

실행: uv run python -m tests.agent.check_select_rule
- 뉴스는 ai_related면 worth_today가 false여도 선별에 들어가고, AI 무관 뉴스는 빠진다
- 도구(MCP·스킬)는 전처럼 ai_related이고 worth_today여야 들어간다
- 재사용 판정(select_memo)도 같은 규칙
- 사용자 후보 단계 입력은 같은 주제 가중치 안에서 별점(중요도) 높은 순, 후보 모델에게 별점을 보여 준다
"""
import asyncio
import json
import random
import sys

from langchain_core.messages import AIMessage

from agent import curator
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
    news = [{"type": "news", "title": f"n{s}", "topic": "industry", "source": "aitimes", "importance": s} for s in (3, 5, 4)]
    news.append({"type": "news", "title": "가중치", "topic": "model_release", "source": "aitimes", "importance": 3})
    pool, _ = curator._pick_pool(news, [], {"model_release": 2})
    check("후보_입력은_가중치_다음_별점_높은_순", [i["title"] for i in pool] == ["가중치", "n5", "n4", "n3"])
    check("후보_프롬프트에_별점_높은_뉴스_먼저", "importance(1~5, 별점)가 높을수록 먼저" in curator.PICK_PROMPT)
    check("선별_프롬프트에_뉴스는_ai_related만", "뉴스(type news)는 ai_related만으로 후보가 된다" in curator.SELECT_PROMPT)


def main() -> int:
    asyncio.run(selection())
    ranking()
    passed = sum(ok for _, ok in results)
    print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
