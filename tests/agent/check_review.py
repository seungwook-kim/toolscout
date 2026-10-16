"""선별 2차 검토 검수 (2026-10-16, agent/review.py). 네트워크·DB·실제 모델을 쓰지 않는다.

실행: uv run python -m tests.agent.check_review
- 통과한 뉴스 중 오늘 새로 판정한 것만 검토에 보낸다(도구·재사용 뉴스는 안 보냄)
- keep false는 선별에서 빠지고, judged의 worth_today가 false·근거가 "2차 검토:"로 바뀐다(select_memo에 최종 판정)
- 형식이 끝내 틀리면 1차 판정을 그대로 두고 큐레이터 형식 실패로 세지 않는다
- curator.run이 검토를 거친 선별을 쓰고 보고(review)를 남긴다
- 선별 프롬프트에 뉴스 기준(true·false), 검토 프롬프트에 두 단계 기준과 "1차 판정 유지"
- 골든셋 fetch_select가 검토에서 뺀 뉴스를 worth_today false로 꺼낸다
"""
import asyncio
import json
import sys

from langchain_core.messages import AIMessage

from agent import curator, review
from agent.structured import Stats
from tests.golden import fetch_select

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("통과 " if ok else "실패 ") + name)


def answer(reply: dict) -> AIMessage:
    return AIMessage(json.dumps(reply, ensure_ascii=False), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})


def fake(sent: list[str], broken: bool = False):
    def call(role, messages, tools=None, **kw):
        system = messages[0].content
        data = json.loads(messages[-1].content.split("<data>\n")[1].split("\n</data>")[0]) if "<data>" in messages[-1].content else []
        if '"reviews"' in system:
            sent.extend(d["title"] for d in data)
            if broken:
                return answer({"reviews": []})
            return answer({"reviews": [{"id": d["id"], "keep": "발언" not in d["title"], "reason": "발언만 있는 기사"} for d in data]})
        if '"judgments"' in system:
            return answer({"judgments": [{"id": d["id"], "ai_related": True, "worth_today": True, "topic": "industry", "importance": 3,
                                          "reason": "1차 통과"} for d in data]})
        if '"groups"' in system:
            return answer({"groups": []})
        if '"empty_reason"' in system:
            return answer({"news": [{"id": 1, "why": "고른 이유"}], "tools": [], "empty_reason": None})
        return answer({"requests": []})
    return call


def item(n: int, title: str, kind: str = "news") -> dict:
    return {"type": kind, "source": "aitimes", "title": title, "url": f"https://review.test/{n}", "summary": "s"}


async def main_async() -> None:
    selected = [item(1, "새 모델 공개"), item(2, "CEO 발언"), item(3, "어제 본 발언"), item(4, "도구 발언", "mcp")]
    judged = [{"url": "https://review.test/1", "title": "새 모델 공개", "worth_today": True, "reason": "1차"},
              {"url": "https://review.test/2", "title": "CEO 발언", "worth_today": True, "reason": "1차"}]
    sent, stats = [], Stats()
    kept, report = await review.run(selected, {"https://review.test/3"}, stats, fake(sent), judged)
    check("새로_판정한_뉴스만_검토(도구·재사용_뉴스_빼고)", sorted(sent) == ["CEO 발언", "새 모델 공개"])
    check("keep_false는_빠짐", [k["title"] for k in kept] == ["새 모델 공개", "어제 본 발언", "도구 발언"] and report["dropped"] == 1)
    check("judged에_최종_판정(worth_today_false·2차_검토_근거)", judged[1]["worth_today"] is False and judged[1]["reason"].startswith("2차 검토:")
          and judged[0]["worth_today"] is True)
    check("검토_호출이_큐레이터_호출_수에_합쳐짐", stats.calls == 1 and stats.unrecovered == 0)
    stats2 = Stats()
    kept2, report2 = await review.run(selected, set(), stats2, fake([], broken=True), None)
    check("형식_실패면_1차_판정_유지·형식_실패로_안_셈", len(kept2) == 4 and report2["failed"] == 1 and stats2.unrecovered == 0 and stats2.calls == 2)
    mem = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": []}
    result = await curator.run([item(1, "새 모델 공개"), item(2, "CEO 발언")], [mem], seed=1, model_call=fake([]))
    check("curator.run이_검토를_거친_선별과_보고를_남김", [i["title"] for i in result["selected"]] == ["새 모델 공개"]
          and result["review"]["dropped"] == 1 and not result["format_failed"]
          and [j["worth_today"] for j in sorted(result["judged"], key=lambda j: j["title"])] == [False, True])


def prompts() -> None:
    check("선별_프롬프트에_뉴스_기준(true·false,_도구_제외)", all(w in curator.SELECT_PROMPT for w in (
        "도구(mcp·skill)에는 쓰지 않는다", "Show HN·GitHub·Hugging Face", "발언·인터뷰·경고·해명·반박만", "고객·도입 사례", "속도·벤치마크를 재 본 글")))
    check("검토_프롬프트에_두_단계·1차_판정_유지", all(w in review.PROMPT for w in ("1) 먼저", "2) 아니면", "1차 판정을 믿고 keep true", "재미로 만든 개인 데모")))
    check("두_프롬프트_구분(fetch_select가_보는_표시)", '"judgments"' not in review.PROMPT and '"reviews"' not in curator.SELECT_PROMPT)


def fetch() -> None:
    def obs(start: str, system: str, data: list, output: dict) -> dict:
        return {"name": "llm:curator", "startTime": start, "input": [{"content": system}, {"content": f"<data>\n{json.dumps(data, ensure_ascii=False)}\n</data>"}],
                "output": {"text": json.dumps(output, ensure_ascii=False)}}
    rows = fetch_select.judgments([
        obs("2", '"reviews"', [{"id": 1, "title": "B"}], {"reviews": [{"id": 1, "keep": False, "reason": "발언"}]}),
        obs("1", '"judgments"', [{"id": 1, "type": "news", "source": "s", "title": "A"}, {"id": 2, "type": "news", "source": "s", "title": "B"}],
            {"judgments": [{"id": 1, "ai_related": True, "worth_today": True, "topic": "industry", "importance": 3},
                           {"id": 2, "ai_related": True, "worth_today": True, "topic": "industry", "importance": 3}]})])
    check("fetch_select가_검토에서_뺀_뉴스를_false로", {r["title"]: r["worth_today"] for r in rows} == {"A": True, "B": False})


def main() -> int:
    asyncio.run(main_async())
    prompts()
    fetch()
    passed = sum(ok for _, ok in results)
    print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
