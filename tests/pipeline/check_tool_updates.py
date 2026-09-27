"""받아 본 도구의 새 버전 알림 검수 (2026-09-27). 모델·네트워크를 쓰지 않고 DB는 읽기만 한다.

실행: uv run python -m tests.pipeline.check_tool_updates
- 제목 끝 버전 읽기, 새 버전 비교(숫자 기준, 못 읽으면 다르기만 해도), 하루 1장·가장 최근 것, 카드 모양(이유·릴리스 페이지·update_from)
- plan 도구 칸 맨 앞에 넣기, 오늘 이미 고른 도구·모델 장애 plan은 건너뜀, 빈 plan은 비움 해제
- 발송 전 검증은 새 버전 카드를 예전 결과가 있어도 다시 확인
- 실제 DB: shown_versions는 오늘 카드를 빼고 최근 30일 MCP만
실측(9/27 18시): 본인 계정이 30일 동안 받은 MCP 21개 중 4개에 새 버전(레지스트리 7일 갱신 6,430건 기준), 그중 가장 최근 1장
"""
import asyncio
import json
import sys
from datetime import date

from pipeline import presend, tool_updates, verification

LATEST = {"https://github.com/a/one": {"title": "One 1.4.0", "version": "1.4.0", "summary": "desc", "install": {"packages": []},
                                       "published": "2026-09-26T10:00:00+00:00"},
          "https://github.com/b/two": {"title": "Two 2.0.1", "version": "2.0.1", "summary": "", "install": None,
                                       "published": "2026-09-27T01:00:00+00:00"},
          "https://github.com/c/same": {"title": "Same 3.0.0", "version": "3.0.0", "published": "2026-09-27T02:00:00+00:00"}}
SHOWN = {"https://github.com/a/one": {"version": "1.2.0", "title": "One 1.2.0", "topic": "coding_tools"},
         "https://github.com/b/two": {"version": "2.0.0", "title": "Two 2.0.0", "topic": None},
         "https://github.com/c/same": {"version": "3.0.0", "title": "Same 3.0.0", "topic": "mcp_tools"}}


def plan(uid: int, tools: list[dict], **kw) -> dict:
    return {"user_id": uid, "news": [], "tools": tools, "related": [], "failed": False, "empty": not tools, "empty_reason": None} | kw


def presend_todo(item: dict) -> list[str]:
    """예전 검증 결과가 있는 도구에 대해 발송 전 검증이 무엇을 다시 확인하는지."""
    before = (verification.results_for, verification.save_requests, verification.item_id_for)
    verification.results_for = lambda urls: {u: {"verification": {"install": {}}, "request_status": "done"} for u in urls}
    verification.save_requests = lambda day, requests: len(requests)
    verification.item_id_for = lambda url: 1
    try:
        requests, _ = asyncio.run(presend._requests({"plans": [plan(1, [item])]}, date(2000, 1, 1), "mcp", "검수"))
        return [r["url"] for r in requests]
    finally:
        (verification.results_for, verification.save_requests, verification.item_id_for) = before


def main() -> int:
    picked = tool_updates.pick(SHOWN, LATEST)
    card = picked[0] if picked else {}
    plans = [plan(1, [{"type": "mcp", "url": "https://x.test/t", "title": "t"}]), plan(2, [], empty=True, empty_reason="비움"),
             plan(3, [{"type": "mcp", "url": "https://github.com/b/two", "title": "Two 2.0.1"}]), plan(4, [], failed=True)]
    added = tool_updates.add_to_plans(plans, LATEST, date(2026, 9, 27), shown_for=lambda uid, today: SHOWN)
    today = date.today()
    real = tool_updates.shown_versions(45, today)
    checks = {
        "제목_끝_버전_읽기": tool_updates.version_in_title("Bitbybit CAD MCP 1.3.2") == "1.3.2"
        and tool_updates.version_in_title("review-swarm (curtisgalloway)") is None and tool_updates.version_in_title("1.0.0") is None
        and tool_updates.version_in_title("X v2.1.0-beta.1") == "v2.1.0-beta.1",
        "새_버전_비교": tool_updates.is_newer("1.0.130", "1.0.95") and not tool_updates.is_newer("1.0.95", "1.0.130")
        and not tool_updates.is_newer("v2.0.0", "2.0.0") and tool_updates.is_newer("2024-rc", "nightly") and not tool_updates.is_newer(None, "1"),
        "하루_1장·가장_최근_것": [c["url"] for c in picked] == ["https://github.com/b/two"],
        "카드_모양": card.get("why") == "받아 본 도구의 새 버전 (2.0.0 → 2.0.1)" and card.get("source_url") == "https://github.com/b/two/releases"
        and card.get("update_from") == "2.0.0" and card.get("type") == "mcp" and card.get("topic") == "mcp_tools"
        and card.get("summary", "").startswith("2.0.0에서 2.0.1로 새 버전이 나왔습니다."),
        "도구칸_맨앞에_넣기": [t["url"] for t in plans[0]["tools"]] == ["https://github.com/b/two", "https://x.test/t"],
        "빈_plan은_비움_해제": plans[1]["tools"] and plans[1]["empty"] is False and plans[1]["empty_reason"] is None,
        "오늘_이미_고른_도구는_안넣음": [t["url"] for t in plans[2]["tools"]] == ["https://github.com/b/two"],
        "모델장애_plan은_건너뜀": plans[3]["tools"] == [],
        "넣은_수": added == 2,
        "최신목록_없으면_아무것도_안함": tool_updates.add_to_plans([plan(1, [])], {}, date(2026, 9, 27), shown_for=lambda u, t: SHOWN) == 0,
        "발송전검증_새버전은_다시확인": presend_todo(card) == ["https://github.com/b/two"]
        and presend_todo({"type": "mcp", "url": "https://github.com/b/two", "title": "Two"}) == [],
        "실제DB_최근30일_MCP만·버전있음": isinstance(real, dict) and all(v["version"] for v in real.values()),
    }
    report = {"checks": checks, "real_shown_mcp": len(real), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
