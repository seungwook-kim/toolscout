"""수집 대체 경로 검수 (2026-09-15 사용자 결정 4·5). 네트워크를 쓰지 않는다.

실행: uv run python -m tests.sources.check_fallbacks
- MCP 레지스트리: 제한 시간 30초 클라이언트, 실패하면 2번 더 시도, 성공하면 마지막 성공 결과 저장
- 3번 다 실패하면 마지막 성공 결과를 다시 쓰고 항목에 "수집 실패, 전날 기준", 실패는 그대로 기록. 성공 결과가 없으면 0건
- 긱뉴스: 항목 안에 외부 링크가 있으면 source_url, 없으면 skip_fetch (해설가가 요약만 쓴다)
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agent.schemas import COLLECTION_STALE
from sources import collect, mcp_registry, rss
from sources.common import SourceResult

NOW = datetime(2026, 9, 15, 0, 0, tzinfo=timezone.utc)
ITEM = {"title": "검수 MCP 1.0", "url": "https://github.com/example/mcp", "published_at": "2026-09-14T00:00:00+00:00",
        "summary": "검수", "source": "mcp_registry", "type": "mcp"}
RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>외부 링크 있음</title><link>https://news.hada.io/topic?id=1</link><pubDate>Mon, 14 Sep 2026 23:00:00 GMT</pubDate>
<description>&lt;p&gt;원문: &lt;a href="https://example.org/post"&gt;링크&lt;/a&gt;&lt;/p&gt;</description></item>
<item><title>외부 링크 없음</title><link>https://news.hada.io/topic?id=2</link><pubDate>Mon, 14 Sep 2026 23:00:00 GMT</pubDate>
<description>&lt;ul&gt;&lt;li&gt;요약만 있다&lt;/li&gt;&lt;/ul&gt;</description></item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class FakeClient:
    def get(self, url):
        return FakeResponse(RSS.encode("utf-8"))


def run_mcp(outcomes: list) -> tuple[SourceResult, list[float]]:
    """outcomes: 시도마다 낼 결과("ok" 또는 오류 문구)."""
    timeouts: list[float] = []
    queue = list(outcomes)
    original_fetch, original_client = mcp_registry.fetch, collect.http_client

    class Client:
        def __init__(self, timeout=20):
            timeouts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_fetch(since, client, *, per_publisher, cache=None, list_since=None):
        outcome = queue.pop(0)
        if outcome == "ok":
            return SourceResult("mcp_registry", items=[dict(ITEM)])
        if outcome == "raise":
            raise RuntimeError("파서 오류")
        return SourceResult("mcp_registry", error=outcome)

    mcp_registry.fetch, collect.http_client = fake_fetch, Client
    try:
        return collect.collect_mcp(NOW, NOW, per_publisher=3, cache=None), timeouts
    finally:
        mcp_registry.fetch, collect.http_client = original_fetch, original_client


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["TOOLSCOUT_CACHE_DIR"] = tmp
        no_cache, _ = run_mcp(["HTTP 500", "ReadTimeout: x", "HTTP 500"])
        recovered, timeouts = run_mcp(["HTTP 500", "raise", "ok"])
        saved = json.loads((Path(tmp) / "mcp_registry_last.json").read_text(encoding="utf-8"))
        reused, _ = run_mcp(["ReadTimeout: x", "HTTP 500", "HTTP 500"])
        os.environ.pop("TOOLSCOUT_CACHE_DIR")
    feed = rss.Feed("geeknews", "https://news.hada.io/rss/news", own_host="hada.io")
    geek = rss.fetch_feed(feed, datetime(2026, 9, 14, tzinfo=timezone.utc), FakeClient())
    by_title = {i["title"]: i for i in geek.items}
    checks = {
        "MCP_제한시간_30초": timeouts == [collect.MCP_TIMEOUT] == [30],
        "MCP_실패하면_2번_더_시도후_성공": recovered.error is None and len(recovered.items) == 1
        and recovered.stats["시도"] == ["HTTP 500", "RuntimeError: 파서 오류", "성공"],
        "MCP_성공하면_마지막_성공결과_저장": saved["date"] == "2026-09-15" and saved["items"][0]["title"] == ITEM["title"],
        "MCP_3번_실패·성공결과_없으면_0건": no_cache.error == "HTTP 500" and no_cache.items == [] and len(no_cache.stats["시도"]) == 3,
        "MCP_3번_실패면_성공결과_재사용·표시": reused.error == "HTTP 500" and len(reused.items) == 1
        and reused.items[0]["collection_note"] == COLLECTION_STALE == "수집 실패, 전날 기준"
        and reused.stats["재사용한_성공_결과_날짜"] == "2026-09-15",
        "긱뉴스_외부링크_있으면_source_url": by_title["외부 링크 있음"].get("source_url") == "https://example.org/post"
        and not by_title["외부 링크 있음"].get("skip_fetch"),
        "긱뉴스_외부링크_없으면_요약만": by_title["외부 링크 없음"].get("skip_fetch") is True
        and "source_url" not in by_title["외부 링크 없음"],
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
