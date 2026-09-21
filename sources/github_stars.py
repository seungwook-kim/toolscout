"""GitHub 별 수 조회와 24시간 캐시 (2026-09-14 사용자 결정).

items.stars·items.stars_checked_at에 저장하고, 24시간 안에 조회한 저장소는 DB 값을 쓴다 (첫날만 전량 조회).
DB가 없거나 실패하면 메모리 캐시만 쓰고 수집은 계속한다. 토큰 값은 출력하지 않는다.
"""
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

log = logging.getLogger("toolscout.stars")

CACHE_HOURS = 24


def repo_url(repo: tuple[str, str]) -> str:
    return f"https://github.com/{repo[0]}/{repo[1]}"


def load_fresh(urls: list[str]) -> dict[str, int | None]:
    """24시간 안에 조회한 저장소의 별 수. 반환: url → stars (조회했지만 실패한 저장소는 None)."""
    if not urls:
        return {}
    try:
        from sqlmodel import select

        import db

        since = datetime.now(timezone.utc) - timedelta(hours=CACHE_HOURS)
        with db.session() as s:
            rows = s.exec(select(db.Item.url, db.Item.stars).where(
                db.Item.url.in_(urls), db.Item.stars_checked_at >= since.replace(tzinfo=None))).all()
        return {url: stars for url, stars in rows}
    except Exception as exc:  # DB 없음·연결 실패는 캐시 없이 진행
        log.warning("별 수 캐시 읽기 건너뜀 (%s)", type(exc).__name__)
        return {}


def save(rows: list[dict]) -> int:
    """조회 결과를 items에 upsert한다. rows: {url, title, version, stars}. 반환: 저장 건수."""
    if not rows:
        return 0
    try:
        from sqlalchemy import func
        from sqlalchemy.dialects.postgresql import insert

        import db

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        unique = {r["url"]: r for r in rows}  # 한 문장 안에 같은 url이 두 번 있으면 upsert가 실패한다
        values = [{"date": date.today(), "type": "mcp", "title": r["title"][:300], "url": r["url"], "source": "mcp_registry",
                   "source_tier": 1, "version": r.get("version"), "stars": r["stars"], "stars_checked_at": now}
                  for r in unique.values()]
        statement = insert(db.Item).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=["url"], set_={"stars": statement.excluded.stars, "stars_checked_at": statement.excluded.stars_checked_at,
                                          # 표시명이 늦게 붙는 경우가 있어 빈 값이 아니면 새 제목으로 채운다 (2026-09-21)
                                          "title": func.coalesce(func.nullif(statement.excluded.title, ""), db.Item.title)})
        with db.get_engine().begin() as connection:
            connection.execute(statement)
        return len(values)
    except Exception as exc:
        log.warning("별 수 캐시 저장 건너뜀 (%s)", type(exc).__name__)
        return 0


def fetch(repo: tuple[str, str], client: httpx.Client, token: str) -> int | None:
    """GitHub API로 별 수를 조회한다. 토큰이 없거나 실패하면 None."""
    if not token:
        return None
    try:
        response = client.get(f"https://api.github.com/repos/{repo[0]}/{repo[1]}",
                              headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        return response.json().get("stargazers_count") if response.status_code == 200 else None
    except httpx.HTTPError:
        return None
