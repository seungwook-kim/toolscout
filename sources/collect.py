"""소스 전체 수집. 뉴스는 24시간, 도구(MCP·스킬)는 7일 창을 쓴다 (계획안 9.2 W1).

소스 하나가 실패해도 나머지로 진행하고 실패를 기록한다 (계획안 부록 B 예외 처리).
"""
from datetime import datetime, timedelta, timezone

from sources import anthropic_skills, hackernews, mcp_registry
from sources.common import SourceResult, error_text, http_client
from sources.rss import FEEDS, fetch_feed

NEWS_WINDOW = timedelta(hours=24)
TOOL_WINDOW = timedelta(days=7)


def collect(now: datetime | None = None, *, mcp_per_publisher: int = mcp_registry.MAX_PER_PUBLISHER,
            hn_min_points: int = hackernews.MIN_POINTS, cache: dict | None = None) -> list[SourceResult]:
    """cache를 넘기면 레지스트리 목록·버전 이력·별 수 조회를 재사용한다 (같은 날 필터 값만 바꿔 재측정할 때)."""
    now = now or datetime.now(timezone.utc)
    news_since, tool_since = now - NEWS_WINDOW, now - TOOL_WINDOW
    jobs = [(feed.name, lambda c, f=feed: fetch_feed(f, news_since, c)) for feed in FEEDS]
    jobs += [
        ("hackernews", lambda c: hackernews.fetch(news_since, c, min_points=hn_min_points)),
        ("mcp_registry", lambda c: mcp_registry.fetch(tool_since, c, per_publisher=mcp_per_publisher, cache=cache)),
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
