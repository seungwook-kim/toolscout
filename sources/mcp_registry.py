"""MCP 공식 레지스트리 공개 API (계획안 9.1 [확인됨]). 창 안에 등록·버전 업된 최신 버전만 모은다."""
from datetime import datetime

import httpx

from sources.common import SourceResult, error_text, make_item, parse_date

URL = "https://registry.modelcontextprotocol.io/v0/servers"
PAGE_SIZE = 100
MAX_PAGES = 20  # 한 번에 최대 2,000건. 넘으면 잘렸다고 기록한다
META_KEY = "io.modelcontextprotocol.registry/official"


def fetch(since: datetime, client: httpx.Client) -> SourceResult:
    result = SourceResult("mcp_registry")
    params: dict = {"updated_since": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "version": "latest", "limit": PAGE_SIZE}
    try:
        for _ in range(MAX_PAGES):
            response = client.get(URL, params=params)
            response.raise_for_status()
            data = response.json()
            for entry in data.get("servers", []):
                result.fetched += 1
                _add(result, entry, since)
            cursor = (data.get("metadata") or {}).get("nextCursor")
            if not cursor:
                break
            params["cursor"] = cursor
        else:
            result.error = f"페이지 상한 {MAX_PAGES}회 도달, 일부만 수집"
    except Exception as exc:
        result.error = error_text(exc)
    return result


def _add(result: SourceResult, entry: dict, since: datetime) -> None:
    server, meta = entry.get("server", {}), entry.get("_meta", {}).get(META_KEY, {})
    if meta.get("status", "active") != "active":
        return
    published = parse_date(meta.get("updatedAt") or meta.get("publishedAt"))
    if published is None or published < since:
        return
    remotes = server.get("remotes") or []
    url = ((server.get("repository") or {}).get("url") or server.get("websiteUrl")
           or (remotes[0].get("url") if remotes else None)
           or f"{URL}?search={server.get('name', '')}")
    title = f"{server.get('title') or server.get('name', '')} {server.get('version', '')}".strip()
    result.items.append(make_item(title=title, url=url, published=published,
                                  summary=server.get("description", ""), source="mcp_registry", type="mcp"))
