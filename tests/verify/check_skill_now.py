"""스킬 발송 전 판독 검수 (2026-09-23). 네트워크·모델·DB를 쓰지 않는다.

왜: 검증은 다음 날 06:00에 도는 구조라, 처음 나가는 스킬 카드에는 늘 "판독 예정"만 붙었다.
스킬 판독은 SKILL.md를 읽고 정규식과 맞춰 보는 일이라 몇 초면 끝나서 하루 실행 안으로 옮겼다.
MCP는 E2B 설치 90초라 그대로 다음 날 06:00에 남는다.

실행: uv run python -m tests.verify.check_skill_now
- 계획에 든 스킬만 판독한다 (MCP는 건드리지 않는다), 관련 카드의 스킬도 포함
- 이미 판독된 스킬은 건너뛴다, 같은 스킬이 여러 사용자에 있어도 한 번
- 한 실행 한도(SKILL_REVIEW_LIMIT)를 지킨다, 요청 모양은 kind=skill·depth=read·skill_url
- 판독이 실패해도 하루 실행은 멈추지 않는다
"""
import asyncio
import json
import sys
from datetime import date

from pipeline import run_daily, verification

DAY = date(2026, 9, 23)


def skill(n: int) -> dict:
    return {"type": "skill", "title": f"검수 스킬 {n}", "url": f"https://github.com/acme/skill-{n}",
            "skill_url": f"https://github.com/acme/skill-{n}"}


def mcp(n: int) -> dict:
    return {"type": "mcp", "title": f"검수 MCP {n}", "url": f"https://github.com/acme/mcp-{n}"}


def curated(plans: list[dict]) -> dict:
    return {"plans": plans}


def run_with(plans: list[dict], reviewed: set[str] = frozenset(), fail: bool = False) -> tuple[dict, dict]:
    """verification·verifier를 가짜로 바꿔 review_skills_now만 돌린다. 반환: (결과, 기록)."""
    log: dict = {"requests": [], "saved": []}
    before = (verification.results_for, verification.save_requests, verification.item_id_for, run_daily.verifier.run)

    async def fake_run(requests, **kwargs):
        log["requests"] = requests
        if fail:
            raise RuntimeError("검수용 실패")
        return {"counts": {"done": len(requests)}, "trace_id": "t-skill"}

    verification.results_for = lambda urls: {u: {"risk_signal": {"level": "normal"}} for u in urls if u in reviewed}
    verification.save_requests = lambda day, requests: log["saved"].append((day, [r["url"] for r in requests])) or len(requests)
    verification.item_id_for = lambda url: int(url.rsplit("-", 1)[-1]) + 100
    run_daily.verifier.run = fake_run
    try:
        return asyncio.run(run_daily.review_skills_now(curated(plans), DAY, None, "http://x/mcp")), log
    finally:
        (verification.results_for, verification.save_requests, verification.item_id_for, run_daily.verifier.run) = before


def main() -> int:
    plans = [{"user_id": 1, "tools": [skill(1), mcp(9)], "related": [skill(2)]},
             {"user_id": 2, "tools": [skill(1), mcp(8)], "related": []}]
    result, log = run_with(plans)
    urls = [r["url"] for r in log["requests"]]

    skipped_result, skipped_log = run_with(plans, reviewed={skill(1)["url"], skill(2)["url"]})
    many, many_log = run_with([{"user_id": 1, "tools": [skill(n) for n in range(10)], "related": []}])
    none_result, none_log = run_with([{"user_id": 1, "tools": [mcp(1)], "related": []}])
    failed, _ = run_with(plans, fail=True)

    checks = {
        "스킬만_판독": urls and all("skill-" in u for u in urls),
        "관련_카드_스킬도_포함": skill(2)["url"] in urls,
        "같은_스킬은_한_번": urls.count(skill(1)["url"]) == 1,
        "요청_모양": all(r["kind"] == "skill" and r["depth"] == "read" and r["install"].get("skill_url") for r in log["requests"]),
        "요청_행_먼저_저장": log["saved"] and log["saved"][0][0] == DAY and set(log["saved"][0][1]) == set(urls),
        "결과_집계": result == {"asked": 2, "done": 2, "skipped": 0, "trace_id": "t-skill"},
        "이미_판독한_것은_건너뜀": skipped_result["asked"] == 0 and skipped_result["skipped"] == 2 and not skipped_log["requests"],
        "한_실행_한도": len(many_log["requests"]) == run_daily.SKILL_REVIEW_LIMIT and many["asked"] == run_daily.SKILL_REVIEW_LIMIT,
        "스킬이_없으면_아무것도_안_함": none_result["asked"] == 0 and not none_log["requests"] and not none_log["saved"],
        "판독_실패해도_실행은_계속": failed["done"] == 0 and failed.get("error") == "RuntimeError",
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
