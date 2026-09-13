"""해커뉴스 Algolia API, 질의 `AI OR LLM` (계획안 9.1 [확인됨]).

Algolia는 질의 문자열의 OR를 연산자로 보지 않아 "AI OR LLM"을 그대로 넣으면 세 단어를 모두 찾는다.
그래서 두 단어를 optionalWords로 넘겨 "AI 또는 LLM" 의미로 묻는다.
"""
from datetime import datetime, timezone

import httpx

from sources.common import SourceResult, error_text, make_item

URL = "https://hn.algolia.com/api/v1/search_by_date"
TERMS = "AI LLM"
PAGE_SIZE = 200


def fetch(since: datetime, client: httpx.Client) -> SourceResult:
    result = SourceResult("hackernews")
    params = {"query": TERMS, "optionalWords": TERMS, "tags": "story",
              "numericFilters": f"created_at_i>{int(since.timestamp())}", "hitsPerPage": PAGE_SIZE}
    try:
        response = client.get(URL, params=params)
        response.raise_for_status()
        hits = response.json().get("hits", [])
    except Exception as exc:
        result.error = error_text(exc)
        return result
    result.fetched = len(hits)
    for hit in hits:
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        published = datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc)
        result.items.append(make_item(title=hit.get("title") or "", url=story_url, published=published,
                                      summary=hit.get("story_text") or "", source="hackernews", type="news"))
    return result
