"""소스 수집 검수 (착수 프롬프트 8번 + 수집 필터). 오늘 실제로 돌려 소스별 건수를 남긴다.

실행: uv run python -m tests.sources.run_today
결과: tests/sources/today_counts.json (건수만), tests/sources/report.md
- 기본 필터(MCP 게시자당 3건·신규 별 수 상위 20·버전 업 상위 10, 해커뉴스 20점)로 측정하고,
  합계가 300건 안팎(±20%)을 넘으면 같은 캐시로 게시자당 2건·30점을 재측정한다 (2026-09-14 사용자 결정)
- 중복 제거 후 건수와 큐레이터 선별 호출 수(20건 묶음)도 남긴다
수집 항목 원문은 저장소에 두지 않고 임시 폴더 캐시에만 둔다 (9번 중복 제거 검수가 읽는다).
"""
import json
import math
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline.dedupe import dedupe
from pipeline.normalize import normalize
from sources.collect import NEWS_WINDOW, TOOL_WINDOW, collect
from sources.rss import FEEDS

SELECT_BATCH = 20

HERE = Path(__file__).parent
CACHE = Path(tempfile.gettempdir()) / "toolscout_items_today.json"
KEYS = {"title", "url", "published_at", "summary", "source", "type"}
EXPECTED = [f.name for f in FEEDS] + ["hackernews", "mcp_registry", "anthropic_skills"]
TARGET, TOLERANCE = 300, 0.2
CONFIGS = [{"mcp_per_publisher": 3, "hn_min_points": 20}, {"mcp_per_publisher": 2, "hn_min_points": 30}]
METHOD = {f.name: f"RSS {f.url}" for f in FEEDS} | {
    "hackernews": "Algolia API, AI 또는 LLM (optionalWords)",
    "mcp_registry": "공식 레지스트리 API /v0/servers, updated_since",
    "anthropic_skills": "GitHub API anthropics/skills 커밋",
}
RULE = {"openai": "날짜 창 필터 (전체 글이 옴)", "aitimes": "시간대 없는 날짜는 KST",
        "reddit_localllama": "User-Agent 필수", "hackernews": "OR는 optionalWords로, points N 이상",
        "mcp_registry": "7일 창, GitHub 저장소, 게시자당 N건, 버전 업 별 50 이상, 별 수 상위 신규 20·버전 업 10",
        "anthropic_skills": "7일 창, PAT 있으면 사용"}
EXCLUDED = [("venturebeat_ai", "RSS https://venturebeat.com/category/ai/feed/", "HTTP 429, 봇 UA 차단, 우회 안 함, 제외")]


def valid_item(item: dict, now: datetime) -> bool:
    published = datetime.fromisoformat(item["published_at"])
    window = NEWS_WINDOW if item["type"] == "news" else TOOL_WINDOW
    return (set(item) == KEYS and item["type"] in {"news", "mcp", "skill"} and item["title"]
            and item["url"].startswith("http") and published.tzinfo is not None
            # 오픈AI처럼 날짜만 주는 피드는 내일 0시로 올 수 있어 상한은 하루 여유를 둔다
            and now - window <= published <= now + NEWS_WINDOW)


def measure(now: datetime, config: dict, cache: dict) -> dict:
    started = time.perf_counter()
    results = collect(now, cache=cache, **config)
    items = [item for r in results for item in r.items]
    grouped = dedupe(normalize(items))  # 큐레이터가 실제로 받는 건수
    return {
        "config": config, "seconds": round(time.perf_counter() - started, 1), "total": len(items), "items": items,
        "after_dedupe": len(grouped), "curator_select_calls": math.ceil(len(grouped) / SELECT_BATCH),
        "results": results,
        "counts": {r.source: {"fetched": r.fetched, "kept": len(r.items), "error": r.error, **({"stats": r.stats} if r.stats else {})}
                   for r in results},
    }


def _mcp_split_ok(results) -> bool:
    stats = next((r.stats for r in results if r.source == "mcp_registry"), {})
    return stats.get("신규_상위", 99) <= 20 and stats.get("버전업_상위", 99) <= 10


def main() -> int:
    now = datetime.now(timezone.utc)
    cache: dict = {}
    runs = [measure(now, CONFIGS[0], cache)]
    if runs[0]["total"] > TARGET * (1 + TOLERANCE):
        runs.append(measure(now, CONFIGS[1], cache))
    final = runs[-1]
    within = final["total"] <= TARGET * (1 + TOLERANCE)
    invalid = [i["source"] for i in final["items"] if not valid_item(i, now)]
    checks = {
        "소스_9곳_모두_실행": [r.source for r in final["results"]] == EXPECTED,
        "정규화_스키마·창_유효": not invalid,
        "제외_소스_수집_안_함": not any(r.source == name for r in final["results"] for name, _, _ in EXCLUDED),
        "실패_소스_없음": not any(r.error for r in final["results"]),
        "MCP_신규20·버전업10_이하": _mcp_split_ok(final["results"]),
    }
    report = {"checked_at": now.isoformat(timespec="seconds"), "target": f"{TARGET}건 ±{int(TOLERANCE * 100)}%",
              "measurements": [{k: v for k, v in run.items() if k not in ("items", "results")} for run in runs],
              "final_config": final["config"], "final_total": final["total"], "within_target": within,
              "invalid_items_by_source": sorted(set(invalid)), "checks": checks, "pass": all(checks.values())}
    (HERE / "today_counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CACHE.write_text(json.dumps(final["items"], ensure_ascii=False), encoding="utf-8")
    write_report(now, runs, within)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


def write_report(now: datetime, runs: list[dict], within: bool) -> None:
    lines = [
        "# 소스 수집 리포트",
        "",
        f"측정: {now.strftime('%Y-%m-%d %H:%M')} UTC · `uv run python -m tests.sources.run_today`로 다시 만든다.",
        f"뉴스 24시간, 도구 7일 창. 목표 {TARGET}건 안팎(±{int(TOLERANCE * 100)}%).",
        "",
    ]
    for run in runs:
        cfg = run["config"]
        lines += [f"## 필터: MCP 게시자당 {cfg['mcp_per_publisher']}건, 해커뉴스 {cfg['hn_min_points']}점 이상",
                  "", "| 소스 | 방식 | 처리 규칙 | 받은 건수 | 남긴 건수 | 상태 |", "|---|---|---|---|---|---|"]
        for name, c in run["counts"].items():
            status = f"실패 ({c['error']})" if c["error"] else "OK"
            lines.append(f"| {name} | {METHOD[name]} | {RULE.get(name, '')} | {c['fetched']} | {c['kept']} | {status} |")
        registry = run["counts"].get("mcp_registry", {}).get("stats")
        if registry:
            lines.append("")
            lines.append("MCP 레지스트리 단계별: " + ", ".join(f"{k} {v}" for k, v in registry.items()))
        lines += ["", f"합계: {run['total']}건 · 중복 제거 후 {run['after_dedupe']}건 · "
                      f"큐레이터 선별 호출 {run['curator_select_calls']}회 · 소요 {run['seconds']}초", ""]
    lines += [f"판정: {'목표 안팎, 확정' if within else '목표 초과, 결정 필요'}", "",
              "## 제외한 소스", "", "| 소스 | 방식 | 사유 |", "|---|---|---|"]
    lines += [f"| {name} | {method} | {reason} |" for name, method, reason in EXCLUDED]
    lines.append("")
    (HERE / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
