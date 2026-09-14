"""소스 전체 수집. 뉴스는 24시간, 도구(MCP·스킬)는 7일 창을 쓴다 (계획안 9.2 W1).

소스 하나가 실패해도 나머지로 진행하고 실패를 기록한다 (계획안 부록 B 예외 처리).
"""
from datetime import datetime, timedelta, timezone

from sources import anthropic_skills, hackernews, mcp_registry
from sources.common import SourceResult, error_text, http_client
from sources.rss import FEEDS, fetch_feed

NEWS_WINDOW = timedelta(hours=24)
TOOL_WINDOW = timedelta(days=7)


def collect(now: datetime | None = None) -> list[SourceResult]:
    now = now or datetime.now(timezone.utc)
    news_since, tool_since = now - NEWS_WINDOW, now - TOOL_WINDOW
    jobs = [(feed.name, lambda c, f=feed: fetch_feed(f, news_since, c)) for feed in FEEDS]
    jobs += [
        ("hackernews", lambda c: hackernews.fetch(news_since, c)),
        ("mcp_registry", lambda c: mcp_registry.fetch(tool_since, c)),
        ("anthropic_skills", lambda c: anthropic_skills.fetch(tool_since, c)),
    ]
    results = []
    with http_client() as client:
        for name, job in jobs:
            try:
                results.append(job(client))
            except Exception as exc:  # 파서 버그도 전체 수집을 멈추지 않게
                results.append(SourceResult(name, error=error_text(exc)))
    return results
