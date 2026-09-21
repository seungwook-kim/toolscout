"""MCP 공식 레지스트리 공개 API (계획안 9.1 [확인됨]). 7일 창 안에 등록·버전 업된 최신 버전을 모은다.

수집 필터 (2026-09-14 사용자 승인)
- 서버 자신의 GitHub 저장소가 있는 것만 (레지스트리 자체 저장소를 적어 둔 경우는 제외)
- 게시자(이름의 / 앞)당 최대 per_publisher건, 최신 게시 순
- 신규 등록은 통과. 버전 업(첫 버전이 창 이전)은 GitHub 별 50 이상만, GITHUB_TOKEN이 없으면 버전 업 제외
- 남은 것 중 신규는 별 수 상위 20건, 버전 업은 상위 10건. 별 수는 items에 24시간 캐시 (sources/github_stars.py)
"""
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import quote, urlsplit

import httpx

from sources import github_stars
from sources.common import SourceResult, error_text, make_item, parse_date

URL = "https://registry.modelcontextprotocol.io/v0/servers"
PAGE_SIZE = 100
MAX_PAGES = 100
META_KEY = "io.modelcontextprotocol.registry/official"
PLACEHOLDER_REPO = ("modelcontextprotocol", "registry")
MAX_PER_PUBLISHER = 3
MIN_STARS_FOR_UPDATE = 50
TOP_NEW, TOP_UPDATES = 20, 10
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
    stars = _Stars(client, os.environ.get("GITHUB_TOKEN", ""), cache)
    stars.preload([repo for _, repo in candidates])
    with ThreadPoolExecutor(WORKERS) as pool:
        kept, counts = _select(by_publisher, since, client, per_publisher, stars, cache, pool)
        list(pool.map(lambda k: stars.get(k[1]), kept))  # 신규도 순위를 매기려고 별 수를 채운다
    rank = lambda k: stars.cache.get(github_stars.repo_url(k[1])) if stars.cache.get(github_stars.repo_url(k[1])) is not None else -1  # noqa: E731
    new = sorted((k for k in kept if k[2] == "new"), key=rank, reverse=True)[:TOP_NEW]
    updates = sorted((k for k in kept if k[2] == "update"), key=rank, reverse=True)[:TOP_UPDATES]
    saved = stars.flush({repo: entry for entry, repo in candidates})  # 버전 업 제외분까지 새로 조회한 값은 모두 저장
    result.stats = {"창_안_active": len(entries), "github_저장소": len(candidates), "게시자": len(by_publisher), **counts,
                    "신규_상위": len(new), "버전업_상위": len(updates), "별수_DB캐시": stars.from_db,
                    "별수_새조회": stars.fetched, "별수_DB저장": saved}
    for entry, repo, _ in new + updates:
        server = entry["server"]
        title = display_title(server)
        item = make_item(title=title, url=github_stars.repo_url(repo), published=_published(entry),
                         summary=server.get("description", ""), source="mcp_registry", type="mcp")
        if install := install_info(server):
            item["install"] = install  # 검증관이 설치 명령·원격 주소를 정할 때 쓴다 (세션 8)
        result.items.append(item)
    return result


def display_title(server: dict) -> str:
    """카드·도구 목록에 쓰는 제목. 레지스트리 표시명(title)이 있으면 그것, 없으면 이름(io.github.x/y)에 버전을 붙인다.

    별 수 캐시 경로가 표시명 없이 이름만 저장해 도구 목록 56건 중 55건이 io.github 형태로 쌓였다 (2026-09-21).
    """
    return f"{server.get('title') or server.get('name', '')} {server.get('version', '')}".strip()


def install_info(server: dict) -> dict | None:
    """레지스트리 server.json에서 설치 정보만: packages(registryType·identifier·version·transport) 3개, remotes(type·url) 3개."""
    packages = [{"registryType": p.get("registryType") or p.get("registry_type"), "identifier": p.get("identifier") or p.get("name"),
                 "version": p.get("version"), "transport": (p.get("transport") or {}).get("type")}
                for p in (server.get("packages") or [])[:3]]
    remotes = [{"type": r.get("type") or r.get("transport_type"), "url": r.get("url")} for r in (server.get("remotes") or [])[:3] if r.get("url")]
    return {k: v for k, v in (("packages", packages), ("remotes", remotes)) if v} or None


class _Stars:
    """별 수 조회: 메모리 → DB 24시간 캐시 → GitHub API. 새로 조회한 값만 모아 DB에 쓴다."""

    def __init__(self, client: httpx.Client, token: str, cache: dict):
        self.client, self.token, self.cache = client, token, cache.setdefault("stars", {})
        self.new: dict[str, int | None] = {}
        self.from_db = self.fetched = 0

    def preload(self, repos: list[tuple[str, str]]) -> None:
        missing = [github_stars.repo_url(r) for r in repos if github_stars.repo_url(r) not in self.cache]
        fresh = github_stars.load_fresh(sorted(set(missing)))
        self.cache.update(fresh)
        self.from_db = len(fresh)

    def get(self, repo: tuple[str, str]) -> int | None:
        url = github_stars.repo_url(repo)
        if url not in self.cache and self.token:
            self.cache[url] = self.new[url] = github_stars.fetch(repo, self.client, self.token)
            self.fetched += 1
        return self.cache.get(url)

    def flush(self, entries_by_repo: dict) -> int:
        rows = []
        for repo, entry in entries_by_repo.items():
            url = github_stars.repo_url(repo)
            if url in self.new:
                server = entry["server"]
                rows.append({"url": url, "title": display_title(server), "version": server.get("version"), "stars": self.new[url]})
        return github_stars.save(rows)


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


def _select(by_publisher: dict, since: datetime, client: httpx.Client, per_publisher: int, stars: _Stars,
            cache: dict, pool: ThreadPoolExecutor):
    """게시자마다 최신 순으로 신규/버전 업을 판정해 per_publisher건까지 고른다. 반환: [(entry, repo, "new"|"update")]."""
    kept, counts = [], {"신규": 0, "버전업_별50이상": 0, "버전업_제외": 0, "게시자_상한으로_제외": 0}
    queues = {pub: list(items) for pub, items in by_publisher.items()}
    accepted: dict[str, int] = defaultdict(int)
    checked: dict[str, int] = defaultdict(int)
    while True:
        batch = [(pub, queue.pop(0)) for pub, queue in queues.items()
                 if queue and accepted[pub] < per_publisher and checked[pub] < per_publisher * MAX_CHECKS_PER_PUBLISHER]
        if not batch:
            break
        firsts = list(pool.map(lambda b: _first_published(b[1][0]["server"]["name"], client, cache), batch))
        updates = [i for i, first in enumerate(firsts) if first is None or first < since]
        update_stars = dict(zip(updates, pool.map(lambda i: stars.get(batch[i][1][1]), updates)))
        for i, (pub, (entry, repo)) in enumerate(batch):
            checked[pub] += 1
            if i not in update_stars:
                counts["신규"] += 1
                kind = "new"
            elif update_stars[i] is not None and update_stars[i] >= MIN_STARS_FOR_UPDATE:
                counts["버전업_별50이상"] += 1
                kind = "update"
            else:
                counts["버전업_제외"] += 1
                continue
            accepted[pub] += 1
            kept.append((entry, repo, kind))
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
