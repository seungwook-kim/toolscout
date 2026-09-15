"""RSS 소스 7곳 (계획안 9.1 [확인됨]).

긱뉴스는 항목 링크(news.hada.io/topic)가 봇에게 403이라, 항목 안의 외부 출처 링크가 있으면 source_url로 두고
없으면 skip_fetch로 표시해 해설가가 요약만 쓰게 한다 (2026-09-15 사용자 결정). 2026-09-15 확인 시 긱뉴스 RSS에는
외부 링크가 들어 있지 않았다.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import feedparser
import httpx

from sources.common import KST, SourceResult, error_text, make_item, parse_date

HREF = re.compile(r"""href=["'](https?://[^"'\s>]+)["']""")


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    naive_tz: timezone = timezone.utc  # 날짜에 시간대가 없을 때 기준
    summary_limit: int | None = None  # 본문이 통째로 오는 피드는 자른다
    own_host: str | None = None  # 항목 링크가 이 도메인이면 원문 대신 항목 안 외부 링크를 찾는다


FEEDS = [
    # 오픈AI는 전체 글이 오므로 날짜 창 필터가 필수다 (collect의 since로 거른다)
    Feed("openai", "https://openai.com/news/rss.xml"),
    Feed("google_ai", "https://blog.google/technology/ai/rss/"),
    Feed("aitimes", "https://www.aitimes.com/rss/allArticle.xml", naive_tz=KST),
    Feed("geeknews", "https://news.hada.io/rss/news", own_host="hada.io"),
    Feed("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    Feed("reddit_localllama", "https://www.reddit.com/r/LocalLLaMA/.rss"),
]
# 벤처비트는 제외: 정직한 봇 User-Agent에 HTTP 429로 차단, 우회하지 않는다 (tests/sources/report.md)


def fetch_feed(feed: Feed, since: datetime, client: httpx.Client) -> SourceResult:
    result = SourceResult(feed.name)
    try:
        response = client.get(feed.url)
        response.raise_for_status()
    except Exception as exc:
        result.error = error_text(exc)
        return result
    parsed = feedparser.parse(response.content)
    result.fetched = len(parsed.entries)
    for entry in parsed.entries:
        published = parse_date(entry.get("published") or entry.get("updated"), feed.naive_tz)
        if published is None or published < since or not entry.get("link"):
            continue
        summary = entry.get("summary", "")
        if feed.summary_limit:
            summary = summary[: feed.summary_limit]
        item = make_item(title=entry.get("title", ""), url=entry["link"], published=published,
                         summary=summary, source=feed.name, type="news")
        if feed.own_host:
            external = external_link(entry, feed.own_host)
            item = item | ({"source_url": external} if external else {"skip_fetch": True})
        result.items.append(item)
    if feed.own_host:
        result.stats = {"외부_출처_링크": sum(1 for i in result.items if i.get("source_url")),
                        "요약만": sum(1 for i in result.items if i.get("skip_fetch"))}
    return result


def external_link(entry, own_host: str) -> str | None:
    """항목 링크 목록과 본문에서 own_host가 아닌 첫 http(s) 링크."""
    body = entry.get("summary", "") + "".join(c.get("value", "") for c in entry.get("content", []) or [])
    candidates = [link.get("href", "") for link in entry.get("links", []) or []] + HREF.findall(body)
    for url in candidates:
        host = (urlsplit(url).hostname or "").lower()
        if url.startswith(("http://", "https://")) and host and not (host == own_host or host.endswith("." + own_host)):
            return url
    return None
