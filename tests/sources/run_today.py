"""소스 수집 검수 (착수 프롬프트 8번). 오늘 실제로 돌려 소스별 건수를 남긴다.

실행: uv run python -m tests.sources.run_today
결과: tests/sources/today_counts.json (건수만), tests/sources/report.md
수집 항목 원문은 저장소에 두지 않고 임시 폴더 캐시에만 둔다 (9번 중복 제거 검수가 읽는다).
"""
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sources.collect import NEWS_WINDOW, TOOL_WINDOW, collect
from sources.rss import FEEDS

HERE = Path(__file__).parent
CACHE = Path(tempfile.gettempdir()) / "toolscout_items_today.json"
KEYS = {"title", "url", "published_at", "summary", "source", "type"}
EXPECTED = [f.name for f in FEEDS] + ["hackernews", "mcp_registry", "anthropic_skills"]
METHOD = {f.name: f"RSS {f.url}" for f in FEEDS} | {
    "hackernews": "Algolia API, AI 또는 LLM (optionalWords)",
    "mcp_registry": "공식 레지스트리 API /v0/servers, updated_since",
    "anthropic_skills": "GitHub API anthropics/skills 커밋",
}
RULE = {"openai": "날짜 창 필터 (전체 글이 옴)", "aitimes": "시간대 없는 날짜는 KST",
        "reddit_localllama": "User-Agent 필수", "hackernews": "OR는 optionalWords로", "mcp_registry": "7일 창, 최신 버전만",
        "anthropic_skills": "7일 창, PAT 있으면 사용"}
EXCLUDED = [("venturebeat_ai", "RSS https://venturebeat.com/category/ai/feed/", "HTTP 429, 봇 UA 차단, 우회 안 함, 제외")]


def valid_item(item: dict, now: datetime) -> bool:
    published = datetime.fromisoformat(item["published_at"])
    window = NEWS_WINDOW if item["type"] == "news" else TOOL_WINDOW
    return (set(item) == KEYS and item["type"] in {"news", "mcp", "skill"} and item["title"]
            and item["url"].startswith("http") and published.tzinfo is not None
            # 오픈AI처럼 날짜만 주는 피드는 내일 0시로 올 수 있어 상한은 하루 여유를 둔다
            and now - window <= published <= now + NEWS_WINDOW)


def main() -> int:
    now = datetime.now(timezone.utc)
    results = collect(now)
    items = [item for r in results for item in r.items]
    invalid = [i["source"] for i in items if not valid_item(i, now)]
    counts = {r.source: {"fetched": r.fetched, "in_window": len(r.items), "error": r.error} for r in results}
    checks = {
        "소스_9곳_모두_실행": [r.source for r in results] == EXPECTED,
        "정규화_스키마·창_유효": not invalid,
        "제외_소스_수집_안_함": not any(r.source == name for r in results for name, _, _ in EXCLUDED),
        "실패는_기록되고_전체는_계속": all(r.error or r.fetched >= 0 for r in results),
    }
    failed = [r.source for r in results if r.error]
    report = {"checked_at": now.isoformat(timespec="seconds"), "total_in_window": len(items), "counts": counts,
              "failed_sources": failed, "invalid_items_by_source": sorted(set(invalid)), "checks": checks,
              "pass": all(checks.values())}
    (HERE / "today_counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CACHE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    write_report(now, counts, len(items))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


def write_report(now: datetime, counts: dict, total: int) -> None:
    lines = [
        "# 소스 수집 리포트",
        "",
        f"측정: {now.strftime('%Y-%m-%d %H:%M')} UTC · `uv run python -m tests.sources.run_today`로 다시 만든다.",
        "원래 09-11 리포트는 저장소에 없어서 이 파일은 새로 측정해 작성했다. 뉴스 24시간, 도구 7일 창 기준.",
        "",
        "| 소스 | 방식 | 처리 규칙 | 받은 건수 | 창 안 건수 | 상태 |",
        "|---|---|---|---|---|---|",
    ]
    for name, c in counts.items():
        status = f"실패 ({c['error']})" if c["error"] else "OK"
        lines.append(f"| {name} | {METHOD[name]} | {RULE.get(name, '')} | {c['fetched']} | {c['in_window']} | {status} |")
    lines += ["", f"창 안 합계: {total}건", "", "## 제외한 소스", "", "| 소스 | 방식 | 사유 |", "|---|---|---|"]
    lines += [f"| {name} | {method} | {reason} |" for name, method, reason in EXCLUDED]
    lines.append("")
    (HERE / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
