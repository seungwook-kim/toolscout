"""정리·중복 제거 검수 (착수 프롬프트 9번). 오늘 데이터로 전후 건수를 남긴다.

실행: uv run python -m tests.pipeline.run_dedupe
오늘 데이터는 tests.sources.run_today가 임시 폴더에 남긴 캐시를 쓰고, 없으면 새로 수집한다.
결과: tests/pipeline/dedupe_counts.json (건수와 묶음 예시 제목만)
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from pipeline.dedupe import dedupe
from pipeline.normalize import canonical_url, clean_text, normalize

HERE = Path(__file__).parent
CACHE = Path(tempfile.gettempdir()) / "toolscout_items_today.json"


def news(title: str, url: str, source: str, at: str = "2026-09-13T01:00:00+00:00") -> dict:
    return {"title": title, "url": url, "published_at": at, "summary": "", "source": source, "type": "news"}


def unit_checks() -> dict:
    same_link = normalize([news("A", "https://x.com/a/?utm_source=rss#top", "geeknews"),
                           news("A", "https://X.com/a", "aitimes")])
    similar = normalize([news("OpenAI releases GPT-5.6 Terra model", "https://a.com/1", "hackernews"),
                         news("OpenAI releases GPT 5.6 Terra model!", "https://b.com/2", "openai"),
                         news("Totally different story", "https://c.com/3", "geeknews")])
    tools = normalize([{**news("io.github.a/notion-mcp 1.0.0", "https://github.com/a/notion-mcp", "mcp_registry"), "type": "mcp"},
                       {**news("io.github.b/notion-mcp 1.0.0", "https://github.com/b/notion-mcp", "mcp_registry"), "type": "mcp"}])
    shared_site = normalize([{**news("com.acme/pricing 1.0.0", "https://acme.com", "mcp_registry"), "type": "mcp"},
                             {**news("com.acme/search 1.0.0", "https://acme.com", "mcp_registry"), "type": "mcp"}])
    link_result, similar_result = dedupe(same_link), dedupe(similar)
    return {
        "추적_파라미터·조각_제거": canonical_url("https://X.com/a/?utm_source=rss&id=3#top") == "https://x.com/a?id=3",
        "HTML_제거": clean_text("<p>Hello&nbsp;<b>AI</b></p>") == "Hello AI",
        "같은_링크_하나로": len(link_result) == 1 and link_result[0]["source"] == "aitimes"
        and link_result[0]["also_reported_by"] == [{"source": "geeknews", "url": "https://x.com/a"}],
        "비슷한_제목_묶음_대표는_공식": len(similar_result) == 2 and similar_result[0]["source"] == "openai"
        and similar_result[0]["also_reported_by"][0]["source"] == "hackernews",
        "MCP는_제목_비슷해도_안_묶음": len(dedupe(tools)) == 2,
        "MCP는_링크_같아도_이름_다르면_안_묶음": len(dedupe(shared_site)) == 2,
    }


def load_today() -> list[dict]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    from sources.collect import collect

    return [item for result in collect() for item in result.items]


def main() -> int:
    raw = load_today()
    cleaned = normalize(raw)
    unique_links = len({f"mcp:{i['title']}" if i["type"] == "mcp" else i["url"] for i in cleaned})
    grouped = dedupe(cleaned)
    merged = [g for g in grouped if g["also_reported_by"] and g["type"] == "news"]
    checks = {**unit_checks(), "오늘_데이터_실행": bool(raw) and len(grouped) <= len(cleaned)}
    report = {
        "before": len(raw),
        "after_normalize": len(cleaned),
        "after_link_dedupe": unique_links,
        "after_title_grouping": len(grouped),
        "by_type_before": dict(Counter(i["type"] for i in raw)),
        "by_type_after": dict(Counter(i["type"] for i in grouped)),
        "news_groups_with_others": len(merged),
        "group_examples": [{"title": g["title"], "source": g["source"],
                            "also": [a["source"] for a in g["also_reported_by"]][:5]} for g in merged[:5]],
        "checks": checks,
        "pass": all(checks.values()),
    }
    (HERE / "dedupe_counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
