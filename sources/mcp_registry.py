"""MCP 공식 레지스트리 공개 API (계획안 9.1 [확인됨]). 7일 창 안에 등록·버전 업된 최신 버전을 모은다.

수집 필터 (2026-09-14 사용자 승인)
- 서버 자신의 GitHub 저장소가 있는 것만 (레지스트리 자체 저장소를 적어 둔 경우는 제외)
- 게시자(이름의 / 앞)당 최대 per_publisher건, 최신 게시 순
- 신규 등록은 통과. 버전 업(첫 버전이 창 이전)은 GitHub 별 50 이상만, GITHUB_TOKEN이 없으면 버전 업 제외
"""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote, urlsplit

import httpx

from sources.common import SourceResult, error_text, make_item, parse_date

URL = "https://registry.modelcontextprotocol.io/v0/servers"
PAGE_SIZE = 100
MAX_PAGES = 100
META_KEY = "io.modelcontextprotocol.registry/official"
PLACEHOLDER_REPO = ("modelcontextprotocol", "registry")
MAX_PER_PUBLISHER = 3
MIN_STARS_FOR_UPDATE = 50
MAX_CHECKS_PER_PUBLISHER = 3  # 게시자당 per_publisher의 이 배수까지만 조회한다
WORKERS = 8


def fetch(since: datetime, client: httpx.Client, *, per_publisher: int = MAX_PER_PUBLISHER,
          cache: dict | None = None) -> SourceResult:
    result = SourceResult("mcp_registry")
    cache = cache if cache is not None else {}
    try:
        entries = cache.get("entries") or _list_updated(since, client)
        cache["entries"] = entries
    except Exception as exc:
        result.error = error_text(exc)
        return result
    result.fetched = len(entries)
    candidates = [(entry, repo) for entry in entries if (repo := github_repo(entry["server"]))]
    by_publisher: dict[str, list] = defaultdict(list)
    for entry, repo in sorted(candidates, key=lambda c: _published(c[0]), reverse=True):
        by_publisher[entry["server"]["name"].split("/")[0]].append((entry, repo))
    token = os.environ.get("GITHUB_TOKEN", "")
    kept, counts = _select(by_publisher, since, client, per_publisher, token, cache)
    result.stats = {"창_안_active": len(entries), "github_저장소": len(candidates), "게시자": len(by_publisher), **counts}
    for entry, repo in kept:
        server = entry["server"]
        title = f"{server.get('title') or server.get('name', '')} {server.get('version', '')}".strip()
        result.items.append(make_item(title=title, url=f"https://github.com/{repo[0]}/{repo[1]}", published=_published(entry),
                                      summary=server.get("description", ""), source="mcp_registry", type="mcp"))
    return result


def _list_updated(since: datetime, client: httpx.Client) -> list[dict]:
    params: dict = {"updated_since": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "version": "latest", "limit": PAGE_SIZE}
    entries = []
    for _ in range(MAX_PAGES):
        response = client.get(URL, params=params)
        response.raise_for_status()
        data = response.json()
        for entry in data.get("servers", []):
            meta = entry.get("_meta", {}).get(META_KEY, {})
            published = parse_date(meta.get("updatedAt") or meta.get("publishedAt"))
            if meta.get("status", "active") == "active" and published is not None and published >= since:
                entry["_published"] = published
                entries.append(entry)
        cursor = (data.get("metadata") or {}).get("nextCursor")
        if not cursor:
            return entries
        params["cursor"] = cursor
    raise RuntimeError(f"페이지 상한 {MAX_PAGES}회 도달")


def _published(entry: dict) -> datetime:
    return entry["_published"]


def github_repo(server: dict) -> tuple[str, str] | None:
    """서버 자신의 GitHub 저장소 (owner, repo). 없거나 레지스트리 자체 저장소면 None."""
    url = (server.get("repository") or {}).get("url") or ""
    parts = urlsplit(url)
    if (parts.hostname or "").lower() not in ("github.com", "www.github.com"):
        return None
    path = [p for p in parts.path.split("/") if p]
    if len(path) < 2:
        return None
    repo = (path[0], path[1].removesuffix(".git"))
    return None if tuple(p.lower() for p in repo) == PLACEHOLDER_REPO else repo


def _select(by_publisher: dict, since: datetime, client: httpx.Client, per_publisher: int, token: str, cache: dict):
    """게시자마다 최신 순으로 신규/버전 업을 판정해 per_publisher건까지 고른다. 조회는 캐시하고 병렬로 한다."""
    kept, counts = [], {"신규": 0, "버전업_별50이상": 0, "버전업_제외": 0, "게시자_상한으로_제외": 0}
    queues = {pub: list(items) for pub, items in by_publisher.items()}
    accepted: dict[str, int] = defaultdict(int)
    checked: dict[str, int] = defaultdict(int)
    with ThreadPoolExecutor(WORKERS) as pool:
        while True:
            batch = [(pub, queue.pop(0)) for pub, queue in queues.items()
                     if queue and accepted[pub] < per_publisher and checked[pub] < per_publisher * MAX_CHECKS_PER_PUBLISHER]
            if not batch:
                break
            names = [entry["server"]["name"] for _, (entry, _) in batch]
            firsts = list(pool.map(lambda n: _first_published(n, client, cache), names))
            updates = [(i, repo) for i, ((_, (_, repo)), first) in enumerate(zip(batch, firsts)) if first is None or first < since]
            stars = dict(zip([i for i, _ in updates], pool.map(lambda r: _stars(r[1], client, token, cache), updates)))
            for i, ((pub, (entry, repo)), first) in enumerate(zip(batch, firsts)):
                checked[pub] += 1
                if i not in stars:
                    counts["신규"] += 1
                elif stars[i] is not None and stars[i] >= MIN_STARS_FOR_UPDATE:
                    counts["버전업_별50이상"] += 1
                else:
                    counts["버전업_제외"] += 1
                    continue
                accepted[pub] += 1
                kept.append((entry, repo))
    counts["게시자_상한으로_제외"] = sum(len(q) for q in queues.values())
    return kept, counts


def _first_published(name: str, client: httpx.Client, cache: dict) -> datetime | None:
    """서버의 첫 버전 게시 시각. 조회 실패면 None(버전 업으로 보고 보수적으로 거른다)."""
    key = f"first:{name}"
    if key not in cache:
        try:
            response = client.get(f"{URL}/{quote(name, safe='')}/versions")
            response.raise_for_status()
            dates = [parse_date(v.get("_meta", {}).get(META_KEY, {}).get("publishedAt")) for v in response.json().get("servers", [])]
            cache[key] = min((d for d in dates if d), default=None)
        except httpx.HTTPError:
            cache[key] = None
    return cache[key]


def _stars(repo: tuple[str, str], client: httpx.Client, token: str, cache: dict) -> int | None:
    """GitHub 별 수. 토큰이 없으면 조회하지 않는다(버전 업 제외 규칙)."""
    if not token:
        return None
    key = f"stars:{repo[0]}/{repo[1]}".lower()
    if key not in cache:
        try:
            response = client.get(f"https://api.github.com/repos/{repo[0]}/{repo[1]}",
                                  headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
            cache[key] = response.json().get("stargazers_count") if response.status_code == 200 else None
        except httpx.HTTPError:
            cache[key] = None
    return cache[key]
