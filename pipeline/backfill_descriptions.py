"""MCP 항목의 비어 있는 원문 설명을 공식 레지스트리에서 채운다 (결정 0020). 한 번 돌리는 도구.

수집이 별 수 캐시 경로로 쌓은 항목은 제목과 별 수만 있고 설명이 없어서(MCP 12,352건 중 11,962건), 질문창 의미 검색이 이름 글자에만 기대고 있었다.
레지스트리 목록에는 서버마다 description이 있으므로 그 원문을 그대로 쓴다(AI가 쓴 글이 아니다). 영어 원문이어도 bge-m3가 한국어 질문과 이어 준다.

- uv run python -m pipeline.backfill_descriptions           : 드라이런(DB에 쓰지 않고 채울 수 있는 건수만 센다)
- uv run python -m pipeline.backfill_descriptions --apply   : 설명이 30자 이하인 MCP 항목의 description을 채우고, 그 항목의 벡터를 지운다
  (지운 벡터는 `python -m pipeline.embed_items --backfill`이 새 설명을 넣어 다시 만든다)
"""
import argparse
import sys
import time

import httpx
from sqlalchemy import text

import config  # noqa: F401  (.env 읽기)
import db
from sources import github_stars
from sources import mcp_registry as registry

MIN_DESCRIPTION = 30  # 이 길이 이하면 비었다고 본다 (수집 코드의 description 최대 길이는 300자)
MAX_LEN = 300
PAGE_RETRIES = 3


def descriptions_from(servers: list[dict]) -> dict[str, str]:
    """레지스트리 서버 목록 -> {GitHub 저장소 주소: 설명}. 저장소가 없거나 설명이 비면 건너뛴다."""
    found: dict[str, str] = {}
    for server in servers:
        repo = registry.github_repo(server)
        description = (server.get("description") or "").strip()
        if repo and description:
            found[github_stars.repo_url(repo)] = description[:MAX_LEN]
    return found


def fetch_servers(client: httpx.Client) -> list[dict]:
    """레지스트리 최신 버전 서버를 모두 받는다(쪽당 100건, 한 쪽씩 순서대로, 쪽 실패는 몇 번 다시 시도)."""
    params: dict = {"version": "latest", "limit": 100}
    servers: list[dict] = []
    while True:
        for attempt in range(PAGE_RETRIES):
            try:
                data = client.get(registry.URL, params=params).json()
                break
            except (httpx.HTTPError, ValueError):
                if attempt == PAGE_RETRIES - 1:
                    raise
                time.sleep(2)
        servers += [entry["server"] for entry in data.get("servers", [])]
        cursor = (data.get("metadata") or {}).get("nextCursor")
        if not cursor:
            return servers
        params["cursor"] = cursor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="DB에 쓴다(없으면 드라이런)")
    args = parser.parse_args(argv)
    with httpx.Client(timeout=60) as client:
        found = descriptions_from(fetch_servers(client))
    with db.get_engine().connect() as conn:
        rows = conn.execute(text("SELECT id, url FROM items WHERE type = 'mcp' AND length(coalesce(description, '')) <= :n"),
                            {"n": MIN_DESCRIPTION}).all()
    fill = [(row.id, found[row.url]) for row in rows if row.url in found]
    print(f"설명이 빈 MCP {len(rows)}건 중 레지스트리로 채울 수 있는 것 {len(fill)}건 (레지스트리 서버 설명 {len(found)}개)")
    if not args.apply:
        print("드라이런이라 DB를 바꾸지 않았다. 쓰려면 --apply")
        return 0
    with db.get_engine().begin() as conn:
        conn.execute(text("UPDATE items SET description = :d WHERE id = :id AND length(coalesce(description, '')) <= :n"),
                     [{"id": item_id, "d": description, "n": MIN_DESCRIPTION} for item_id, description in fill])
    try:  # 벡터 표가 아직 없으면 지울 것도 없다. 위 쓰기와 같은 거래에 두면 실패가 쓰기까지 되돌리므로 따로 한다
        with db.get_engine().begin() as conn:
            conn.execute(text("DELETE FROM item_embeddings WHERE item_id = ANY(:ids)"), {"ids": [item_id for item_id, _ in fill]})
    except Exception as exc:
        print(f"벡터 지우기를 건너뜀({type(exc).__name__})")
    print(f"description {len(fill)}건을 채우고 그 항목의 벡터를 지웠다. 이어서: uv run python -m pipeline.embed_items --backfill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
