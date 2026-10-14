"""RSS 소스 7곳 (계획안 9.1 [확인됨]).

긱뉴스는 항목 링크(news.hada.io/topic)가 봇에게 403이라, 항목 안의 외부 출처 링크가 있으면 source_url로 두고
없으면 skip_fetch로 표시해 해설가가 요약만 쓰게 한다 (2026-09-15 사용자 결정). 2026-09-15 확인 시 긱뉴스 RSS에는
외부 링크가 들어 있지 않았다.
레딧 글 페이지는 서버(Railway)에서 읽으면 매번 HTTP 403이다(10/13·10/14 실측 17번 모두). 피드에는 글 본문이 그대로 오므로
글 본문(SC_OFF~SC_ON)을 원문(source_text)으로 쓰고, 링크 글이면 링크가 가리키는 바깥 글을 source_url로 읽게 한다.
그림·영상만 있는 글은 읽을 원문이 없어 skip_fetch (2026-10-14 사용자 결정). 차단을 우회하지 않는다
"""
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import feedparser
import httpx

from sources.common import KST, SourceResult, error_text, make_item, parse_date

HREF = re.compile(r"""href=["'](https?://[^"'\s>]+)["']""")
POST_BODY = re.compile(r"<!-- SC_OFF -->(.*?)<!-- SC_ON -->", re.S)  # 레딧 글 본문
POST_LINK = re.compile(r"""<a href=["'](https?://[^"'\s>]+)["']>\[link\]</a>""")  # 레딧 글이 가리키는 주소
REDDIT_HOSTS = ("reddit.com", "redd.it")
POST_TEXT_LIMIT = 3000  # fetch_article 본문 상한(mcp_server.ARTICLE_LIMIT)과 같게


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    naive_tz: timezone = timezone.utc  # 날짜에 시간대가 없을 때 기준
    summary_limit: int | None = None  # 본문이 통째로 오는 피드는 자른다
    own_host: str | None = None  # 항목 링크가 이 도메인이면 원문 대신 항목 안 외부 링크를 찾는다
    post_body: bool = False  # 항목 본문이 글 원문 그 자체인 피드(레딧). reddit_post로 원문·바깥 링크를 나눈다


FEEDS = [
    # 오픈AI는 전체 글이 오므로 날짜 창 필터가 필수다 (collect의 since로 거른다)
    Feed("openai", "https://openai.com/news/rss.xml"),
    Feed("google_ai", "https://blog.google/technology/ai/rss/"),
    Feed("aitimes", "https://www.aitimes.com/rss/allArticle.xml", naive_tz=KST),
    Feed("geeknews", "https://news.hada.io/rss/news", own_host="hada.io"),
    Feed("techcrunch_ai", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    Feed("reddit_localllama", "https://www.reddit.com/r/LocalLLaMA/.rss", post_body=True),
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
        if feed.post_body:
            item = item | reddit_post(summary)
        result.items.append(item)
    if feed.own_host or feed.post_body:
        result.stats = {"외부_출처_링크": sum(1 for i in result.items if i.get("source_url")),
                        "요약만": sum(1 for i in result.items if i.get("skip_fetch"))}
    if feed.post_body:
        result.stats["글_본문"] = sum(1 for i in result.items if i.get("source_text"))
    return result


def reddit_post(body: str) -> dict:
    """레딧 피드 항목 본문(HTML) 하나를 나눈다. 반환: summary(글 본문 글자) + 다음 중 하나
    - 링크 글([link]가 바깥 주소): source_url = 그 주소. 원문은 링크가 가리키는 글이다
    - 본문 글: source_text = 글 본문(원문 그 자체), 본문 안 첫 바깥 링크가 있으면 source_url로 덧붙여 읽는다
    - 그림·영상만 있는 글: skip_fetch"""
    match = POST_BODY.search(body)
    text = plain_text(match.group(1))[:POST_TEXT_LIMIT] if match else ""
    link = POST_LINK.search(body)
    target = html.unescape(link.group(1)) if link else None
    if target and not is_reddit(target):
        return {"summary": text, "source_url": target}
    if text:
        inner = next((html.unescape(u) for u in HREF.findall(match.group(1)) if not is_reddit(html.unescape(u))), None)
        return {"summary": text, "source_text": text} | ({"source_url": inner} if inner else {})
    return {"summary": text, "skip_fetch": True}


def is_reddit(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in REDDIT_HOSTS)


def plain_text(fragment: str) -> str:
    """HTML 조각을 글자로. 문단·줄바꿈은 줄로 남긴다."""
    text = re.sub(r"</p>|<br\s*/?>|</li>", "\n", fragment)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    lines = (re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def external_link(entry, own_host: str) -> str | None:
    """항목 링크 목록과 본문에서 own_host가 아닌 첫 http(s) 링크."""
    body = entry.get("summary", "") + "".join(c.get("value", "") for c in entry.get("content", []) or [])
    candidates = [link.get("href", "") for link in entry.get("links", []) or []] + HREF.findall(body)
    for url in candidates:
        host = (urlsplit(url).hostname or "").lower()
        if url.startswith(("http://", "https://")) and host and not (host == own_host or host.endswith("." + own_host)):
            return url
    return None
