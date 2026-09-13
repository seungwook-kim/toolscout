"""RSS 소스 7곳 (계획안 9.1 [확인됨])."""
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx

from sources.common import KST, SourceResult, error_text, make_item, parse_date


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    naive_tz: timezone = timezone.utc  # 날짜에 시간대가 없을 때 기준
    summary_limit: int | None = None  # 본문이 통째로 오는 피드는 자른다


FEEDS = [
    # 오픈AI는 전체 글이 오므로 날짜 창 필터가 필수다 (collect의 since로 거른다)
    Feed("openai", "https://openai.com/news/rss.xml"),
    Feed("google_ai", "https://blog.google/technology/ai/rss/"),
    Feed("aitimes", "https://www.aitimes.com/rss/allArticle.xml", naive_tz=KST),
    Feed("geeknews", "https://news.hada.io/rss/news"),
    Feed("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    Feed("venturebeat_ai", "https://venturebeat.com/category/ai/feed/", summary_limit=500),
    Feed("reddit_localllama", "https://www.reddit.com/r/LocalLLaMA/.rss"),
]


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
        result.items.append(make_item(title=entry.get("title", ""), url=entry["link"], published=published,
                                      summary=summary, source=feed.name, type="news"))
    return result
