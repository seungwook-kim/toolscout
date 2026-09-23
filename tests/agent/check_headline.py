"""오늘의 큰 소식 검수 (2026-09-23). 가짜 모델로 확인한다. 네트워크·DB를 쓰지 않는다.

실행: uv run python -m tests.agent.check_headline
- 여러 곳이 다룬 소식이 뽑히고 대표는 공식 발표 > 매체 > 커뮤니티 / 점수 = 최고 중요도 + 다룬 곳 - 1 + 공식
- 3곳 미만이면 없음, 중요도 5는 2곳부터 / 중요도 3 미만은 후보 아님 / 모델 장애면 없음
- 두 번째도 8점 이상이면 2칸, 8점 미만이면 1칸
- 사용자 뉴스 맨 위에 고정, 같은 소식 다른 기사는 빠지고 전체 5장, rank 다시 매김, 빈 브리핑이면 비움 해제
- 이미 본 소식이거나 주제 가중치 -5면 그 사용자에게 안 넣음 / plan 실패면 그대로
- 선별 판정에 importance가 없으면 3 / 카드 규격 headline 칸 / 메일에 "오늘의 큰 소식" 표시
- curator.run이 큰 소식을 사용자마다 붙이고 결과에 요약을 남긴다
"""
import asyncio
import json
import sys

from langchain_core.messages import AIMessage

import models
from agent import curator, headline, schemas
from agent.structured import Stats
from pipeline import briefing_mail

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


def news(n, title, source="hackernews", importance=4, topic="model_release"):
    return {"type": "news", "title": title, "url": f"https://x.test/{n}", "source": source, "importance": importance,
            "topic": topic, "reason": "r"}


def answer(text):
    return lambda role, messages, tools=None: AIMessage(text, usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


OPUS = [news(1, "Opus 5.5 공개", "aitimes", 5), news(2, "Anthropic releases Opus 5.5", "techcrunch_ai", 5),
        news(3, "Claude Opus 5.5 출시", "geeknews", 4)]
GPT = [news(4, "Introducing GPT-6", "openai", 5), news(5, "GPT-6 공개", "aitimes", 4)]
SMALL = [news(6, "작은 프로젝트", importance=2), news(7, "업계 단신", importance=3, topic="industry")]


async def main() -> None:
    selected = OPUS + GPT + SMALL
    # 후보는 중요도 >= 3, 중요도 > 등급 순: 1(5,2) 2(5,2) 4(5,1) 3(4,3) 5(4,2) 7(3,9) → 번호는 그 순서
    pool = sorted([i for i in selected if i["importance"] >= 3], key=lambda i: (-i["importance"], headline._tier(i)))
    ids = {i["url"]: n for n, i in enumerate(pool, 1)}
    groups = [[ids[i["url"]] for i in OPUS], [ids[i["url"]] for i in GPT]]
    tops = await headline.pick(selected, Stats(), answer(json.dumps({"groups": groups})))
    top = tops[0]
    check("세 곳이 다룬 소식이 뽑힘", top["url"] in {i["url"] for i in OPUS} and top["coverage"] == 3)
    check("대표는 매체 기사(공식 없음), 점수 = 5 + 2 + 0", top["source"] in ("aitimes", "techcrunch_ai") and top["score"] == 7)
    check("두 번째가 8점 미만이면 1칸 (GPT 7점)", len(tops) == 1)
    only_gpt = await headline.pick(selected, Stats(), answer(json.dumps({"groups": [groups[1]]})))
    check("중요도 5는 두 곳부터, 대표는 공식 발표", len(only_gpt) == 1 and only_gpt[0]["source"] == "openai" and only_gpt[0]["score"] == 7)
    big = OPUS + [news(12, "Opus 5.5 분석", "hackernews", 5)] + GPT + [news(13, "GPT-6 후기", "geeknews", 5), news(14, "GPT-6 소식", "techcrunch_ai", 4)]
    # 오퍼스 4곳·최고 5·공식 없음 = 8, GPT 4곳·최고 5·공식 = 9
    pool = sorted(big, key=lambda i: (-i["importance"], headline._tier(i)))
    gid = {i["url"]: n for n, i in enumerate(pool, 1)}
    two = await headline.pick(big, Stats(), answer(json.dumps({"groups": [[gid[i["url"]] for i in big[:4]], [gid[i["url"]] for i in big[4:]]]})))
    check("두 번째도 8점 이상이면 2칸, 점수 순", [t["score"] for t in two] == [9, 8] and two[0]["source"] == "openai")
    none = await headline.pick(selected, Stats(), answer('{"groups": []}'))
    check("한 곳씩만 다뤘으면 없음", none == [])
    low = [news(8, "a", importance=4), news(9, "b", importance=4)]
    check("중요도 4 두 곳은 없음(3곳부터)", await headline.pick(low, Stats(), answer('{"groups": [[1, 2]]}')) == [])
    check("중요도 3 미만은 후보 아님", await headline.pick(SMALL[:1] * 3, Stats(), answer('{"groups": [[1, 2, 3]]}')) == [])

    def down(role, messages, tools=None):
        raise models.ModelUnavailable("explainer", ["groq 503"])
    check("모델 장애면 없음", await headline.pick(selected, Stats(), down) == [])

    plan = {"news": [{**OPUS[1], "rank": 1}, {**GPT[0], "rank": 2}, {**SMALL[1], "rank": 3}, {**news(10, "c"), "rank": 4},
                     {**news(11, "d"), "rank": 5}], "tools": [], "failed": False, "empty": False}
    memory = {"seen_urls": [], "weights": {"model_release": 0}}
    out = headline.attach(json.loads(json.dumps(plan)), [top], memory)
    check("맨 위 고정·같은 소식 빠짐·전체 5장·rank 다시", out["news"][0]["url"] == top["url"] and out["news"][0]["headline"]
          and OPUS[1]["url"] not in [i["url"] for i in out["news"][1:]] and len(out["news"]) == 5
          and [i["rank"] for i in out["news"]] == [1, 2, 3, 4, 5])
    empty = headline.attach({"news": [], "tools": [], "failed": False, "empty": True, "empty_reason": "없음"}, [top], memory)
    check("빈 브리핑이면 비움 해제", not empty["empty"] and len(empty["news"]) == 1)
    seen = headline.attach(json.loads(json.dumps(plan)), [top], {"seen_urls": [OPUS[2]["url"]], "weights": {}})
    blocked = headline.attach(json.loads(json.dumps(plan)), [top], {"seen_urls": [], "weights": {"model_release": -5}})
    failed = headline.attach({"news": [], "tools": [], "failed": True}, [top], memory)
    both = headline.attach(json.loads(json.dumps(plan)), two, memory)
    check("2칸이면 맨 위 둘, 나머지 3장, 같은 소식 빠짐", [i["url"] for i in both["news"][:2]] == [two[0]["url"], two[1]["url"]]
          and len(both["news"]) == 5 and not {i["url"] for i in both["news"][2:]} & {u for t in two for u in t["group_urls"]})
    check("본 소식·가중치 -5·실패 plan에는 안 넣음", seen["news"] == plan["news"] and blocked["news"] == plan["news"] and failed["news"] == [])

    check("판정에 importance 없으면 3", schemas.Judgment(id=1, ai_related=True, worth_today=True, topic="industry", reason="rr").importance == 3)
    card = {"type": "news", "title": "Opus 5.5 공개", "url": "https://x.test/1", "summary_ko": "요약.", "for_me": "나한테.",
            "why_this_card": "이유", "relevance": 4, "source_checked": True, "trace_id": "t", "headline": True}
    check("카드 규격에 headline", schemas.Card(**card).headline)
    html, text = briefing_mail._card_html(card), briefing_mail._card_text(card)
    check("메일에 오늘의 큰 소식 표시", briefing_mail.HEADLINE_LABEL in html and f"[{briefing_mail.HEADLINE_LABEL}]" in text
          and briefing_mail.HEADLINE_LABEL not in briefing_mail._card_html(card | {"headline": False}))

    items = [{k: v for k, v in i.items() if k not in ("importance", "topic", "reason")} | {"summary": "s"} for i in OPUS + GPT]

    def fake(role, messages, tools=None):
        system, body = messages[0].content, messages[-1].content
        if '"judgments"' in system:
            data = json.loads(body.split("<data>\n")[1].split("\n</data>")[0])
            reply = {"judgments": [{"id": d["id"], "ai_related": True, "worth_today": True, "topic": "model_release",
                                    "importance": 5 if "Opus" in d["title"] else 3, "reason": "판정"} for d in data]}
        elif '"groups"' in system:
            data = json.loads(body.split("<data>\n")[1].split("\n</data>")[0])
            opus = [d["id"] for d in data if "Opus" in d["title"]]
            reply = {"groups": [opus] if len(opus) > 1 else []}
        elif '"empty_reason"' in system:
            reply = {"news": [{"id": 1, "why": "고른 이유"}], "tools": [], "empty_reason": None}
        else:
            reply = {"requests": []}
        return AIMessage(json.dumps(reply, ensure_ascii=False), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    mem = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": []}
    result = await curator.run(items, [mem, mem | {"user_id": 2}], seed=1, model_call=fake)
    check("curator.run이 사용자마다 큰 소식을 붙이고 요약을 남김",
          all(p["news"] and p["news"][0].get("headline") for p in result["plans"]) and [h["coverage"] for h in result["headlines"]] == [3])


asyncio.run(main())
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
