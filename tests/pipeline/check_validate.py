"""검증 노드 마지막 수단 검수 (2026-10-14). 모델을 부르지 않는다(다시 쓰기는 가짜).

실행: uv run python -m tests.pipeline.check_validate
- for_me가 여러 문장이고 다시 써도 여러 문장이면 첫 문장만 남겨 살린다(고친 내용 기록)
- 다시 쓴 카드가 한 문장이면 그것을 쓴다(마지막 수단 안 씀) / 다시 쓰기가 형식 실패면 원래 카드의 첫 문장
- 첫 문장이 20자 미만이거나 다른 문제(한글 비율)면 지금처럼 뺀다 / 문제없는 카드는 다시 쓰지 않는다
"""
import asyncio
import json
import sys

from pipeline import validate

TWO = "Claude Code와 MCP 설정을 여러 도구에 나눠 관리하고 있다면 한곳에서 배포하는 방식을 참고할 수 있습니다. 다만 아직 초기 버전입니다."
FIRST = "Claude Code와 MCP 설정을 여러 도구에 나눠 관리하고 있다면 한곳에서 배포하는 방식을 참고할 수 있습니다."
ONE = "Claude Code 설정을 한곳에서 관리하는 방식을 참고할 수 있지만 아직 초기 버전입니다."


def card(title: str, for_me: str, summary: str = "여러 AI 도구의 MCP 설정을 한곳에서 맞추는 도구가 나왔습니다.") -> dict:
    url = f"https://github.com/example/{title}"
    return {"type": "mcp", "title": title, "url": url, "summary_ko": summary, "for_me": for_me, "why_this_card": "검수 이유",
            "pros": [{"text": "설정 한곳에서 관리", "evidence_url": url}], "cons": [], "relevance": 4,
            "source_checked": True, "trace_id": "t-validate"}


def main() -> int:
    english = "This tool syncs MCP config across many AI coding tools for you."
    drafts = [card("good", ONE), card("two-two", TWO), card("two-one", TWO), card("two-broken", TWO),
              card("short-first", "참고할 만합니다. 다만 Claude Code와 MCP 설정을 한곳에서 관리하는 방식은 아직 초기 버전입니다."),
              card("english", english, summary=english)]
    redo_answer = {"two-two": {"status": "card", "card": card("two-two", TWO)},
                   "two-one": {"status": "card", "card": card("two-one", ONE)},
                   "two-broken": {"status": "format_failed", "reason": "형식 실패 2회"},
                   "short-first": {"status": "card", "card": card("short-first", "참고할 만합니다. 다만 아직 초기 버전입니다.")},
                   "english": {"status": "card", "card": card("english", english, summary=english)}}
    asked: list[str] = []

    async def redo(item, reason):
        asked.append(item["title"])
        return redo_answer[item["title"]]

    items = {d["url"]: {"title": d["title"]} for d in drafts}
    result = asyncio.run(validate.run_user({"user_id": 1, "cards": drafts, "rejected": [], "format_failed": []}, items, redo))
    kept = {c["title"]: c for c in result["cards"]}
    fixed = {f["title"]: f["fixes"] for f in result["fixed"]}
    excluded = {e["title"]: e["reasons"] for e in result["excluded"]}
    checks = {
        "문제없는_카드는_다시_안씀": "good" not in asked and kept["good"]["for_me"] == ONE,
        "다시써도_두문장이면_첫문장만": kept["two-two"]["for_me"] == FIRST and any("첫 문장" in f for f in fixed["two-two"]),
        "다시쓴_카드가_한문장이면_그것": kept["two-one"]["for_me"] == ONE and "two-one" not in fixed,
        "다시쓰기_형식실패면_원래카드_첫문장": kept["two-broken"]["for_me"] == FIRST,
        "첫문장_20자_미만이면_뺌": "short-first" in excluded and "short-first" not in kept,
        "다른_문제는_그대로_뺌": "english" in excluded and any("한글 비율" in r for r in excluded["english"]),
        "다시쓰기_횟수": result["retried"] == 5,
        "순위_다시_매김": [c["rank"] for c in result["cards"]] == [1, 2, 3, 4],
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
