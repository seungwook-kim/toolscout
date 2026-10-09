"""MCP 레지스트리 목록 받기 검수 (2026-10-09). 가짜 클라이언트만 쓰고 네트워크·모델을 쓰지 않는다.

실행: uv run python -m tests.sources.check_mcp_list
- 목록 창 48시간 파라미터(updated_since)가 요청에 실린다
- 쪽 상한·시간 예산을 넘으면 예외 없이 받은 만큼 돌려주고 stats["부분_수집"]에 쪽 수·이유를 남긴다
- 한 쪽이 실패하면 그 쪽만 다시 받고(앞 쪽은 다시 안 받음), 첫 쪽부터 끝내 실패하면 오류
- 기존 선택 규칙(게시자당 3·새 20·버전업 10·별 50)은 그대로
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

from sources import collect, github_stars, mcp_registry
from sources.mcp_registry import META_KEY

NOW = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
SINCE = NOW - collect.TOOL_WINDOW
LIST_SINCE = NOW - mcp_registry.LIST_WINDOW
FRESH = (NOW - timedelta(hours=1)).isoformat()


def entry(name: str, first: str | None = None) -> dict:
    server = {"name": name, "version": "1.0.0", "description": "검수",
              "repository": {"url": f"https://github.com/{name.replace('/', '-')}/repo"}}
    return {"server": server, "_meta": {META_KEY: {"status": "active", "updatedAt": FRESH, "publishedAt": first or FRESH}}}


class Resp:
    def __init__(self, payload=None, status=200):
        self.payload, self.status = payload, status

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("fail", request=httpx.Request("GET", "http://x"), response=httpx.Response(self.status))

    def json(self):
        return self.payload


class Fake:
    """목록 쪽은 pages 순서대로. 쪽마다 값이 예외면 던지고, 같은 쪽을 다시 부르면 다음 값을 쓴다. 버전 이력은 versions."""

    def __init__(self, pages: list, versions: dict | None = None):
        self.pages, self.versions, self.calls = pages, versions or {}, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if url.endswith("/versions"):
            name = url.rsplit("/", 2)[-2].replace("%2F", "/")
            return Resp({"servers": [{"_meta": {META_KEY: {"publishedAt": self.versions.get(name, FRESH)}}}]})
        page = self.pages[int((params or {}).get("cursor", 0))]
        if isinstance(page, list):  # 이 쪽의 시도 목록: 앞에서부터 하나씩 소비
            outcome = page.pop(0) if len(page) > 1 else page[0]
        else:
            outcome = page
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def list_calls(self):
        return [c for c in self.calls if not c[0].endswith("/versions")]


def page(names: list[str], cursor: int | None) -> Resp:
    return Resp({"servers": [entry(n) for n in names], "metadata": {"nextCursor": str(cursor)} if cursor is not None else {}})


def main() -> int:
    original = (mcp_registry.MAX_PAGES, mcp_registry.LIST_BUDGET, mcp_registry.PAGE_RETRY_WAIT)
    mcp_registry.PAGE_RETRY_WAIT = 0
    saved_stars = (github_stars.load_fresh, github_stars.save, os.environ.get("GITHUB_TOKEN"))
    github_stars.load_fresh, github_stars.save = (lambda urls: {}), (lambda rows: 0)  # DB·GitHub를 부르지 않는다
    os.environ["GITHUB_TOKEN"] = ""
    checks = {}
    try:
        # 1. 48시간 파라미터와 쪽 타임아웃
        fake = Fake([page(["a/1"], 1), page(["b/1"], None)])
        got = mcp_registry._list_updated(LIST_SINCE, fake, {})
        first = fake.list_calls()[0]
        checks["48시간_파라미터"] = first[1]["updated_since"] == "2026-10-07T00:00:00Z" and len(got) == 2
        checks["쪽_타임아웃_30초이하"] = all(c[2] <= mcp_registry.PAGE_TIMEOUT == 30 for c in fake.list_calls())
        # 2. 쪽 상한
        mcp_registry.MAX_PAGES = 2
        partial = {}
        got = mcp_registry._list_updated(LIST_SINCE, Fake([page(["a/1"], 1), page(["b/1"], 2), page(["c/1"], None)]), partial)
        checks["쪽_상한_부분결과"] = len(got) == 2 and partial == {"받은_쪽수": 2, "이유": "쪽 상한 2쪽"}
        mcp_registry.MAX_PAGES = original[0]
        # 3. 시간 예산 (예산 0초: 첫 쪽은 받고 둘째부터 멈춘다)
        mcp_registry.LIST_BUDGET = 0
        partial = {}
        got = mcp_registry._list_updated(LIST_SINCE, Fake([page(["a/1"], 1), page(["b/1"], None)]), partial)
        checks["시간_예산_부분결과"] = len(got) == 1 and partial["받은_쪽수"] == 1 and "시간 예산" in partial["이유"]
        mcp_registry.LIST_BUDGET = original[1]
        # 4. 한 쪽 실패 후 그 쪽만 재시도
        boom = httpx.ReadTimeout("느림")
        fake = Fake([page(["a/1"], 1), [boom, Resp(status=500), page(["b/1"], None)]])
        partial = {}
        got = mcp_registry._list_updated(LIST_SINCE, fake, partial)
        cursors = [c[1].get("cursor") for c in fake.list_calls()]
        checks["쪽_실패_그_쪽만_재시도"] = len(got) == 2 and not partial and cursors == [None, "1", "1", "1"]
        # 5. 중간 쪽이 끝내 실패하면 받은 만큼, 첫 쪽부터 실패하면 오류
        fake = Fake([page(["a/1"], 1), boom])
        partial = {}
        got = mcp_registry._list_updated(LIST_SINCE, fake, partial)
        checks["중간_쪽_끝내_실패_부분결과"] = len(got) == 1 and "쪽 실패" in partial["이유"] and len(fake.list_calls()) == 1 + 3
        result = mcp_registry.fetch(SINCE, Fake([boom]), list_since=LIST_SINCE, cache={})
        checks["첫_쪽부터_실패면_오류"] = bool(result.error) and result.items == []
        # 6. fetch: stats 부분 수집, 캐시 안 함
        mcp_registry.MAX_PAGES = 1
        cache = {}
        result = mcp_registry.fetch(SINCE, Fake([page(["a/1"], 1), page(["b/1"], None)]), list_since=LIST_SINCE, cache=cache)
        checks["fetch_부분수집_stats"] = result.error is None and result.stats["부분_수집"] == {"받은_쪽수": 1, "이유": "쪽 상한 1쪽"} \
            and "entries" not in cache and result.fetched == 1
        mcp_registry.MAX_PAGES = original[0]
        # 7. 선택 규칙: 게시자당 3건, 새 서버만(첫 게시일이 창 안)
        names = [f"pub/{i}" for i in range(5)] + [f"other/{i}" for i in range(2)]
        result = mcp_registry.fetch(SINCE, Fake([page(names, None)]), per_publisher=3, list_since=LIST_SINCE, cache={})
        titles = [i["title"] for i in result.items]
        checks["게시자당_3건"] = sum(t.startswith("pub/") for t in titles) == 3 and sum(t.startswith("other/") for t in titles) == 2
        # 8. 버전 업은 별 토큰이 없으면 제외 (첫 게시일이 창 이전)
        old = (SINCE - timedelta(days=30)).isoformat()
        result = mcp_registry.fetch(SINCE, Fake([page(["old/1"], None)], {"old/1": old}), list_since=LIST_SINCE, cache={"stars": {}})
        checks["버전업_별_없으면_제외"] = result.items == [] and result.stats["버전업_제외"] == 1
        checks["상수_값"] = (mcp_registry.MAX_PER_PUBLISHER, mcp_registry.TOP_NEW, mcp_registry.TOP_UPDATES,
                          mcp_registry.MIN_STARS_FOR_UPDATE) == (3, 20, 10, 50) and mcp_registry.LIST_WINDOW == timedelta(hours=48)
    finally:
        github_stars.load_fresh, github_stars.save = saved_stars[:2]
        os.environ["GITHUB_TOKEN"] = saved_stars[2] or ""
        mcp_registry.MAX_PAGES, mcp_registry.LIST_BUDGET, mcp_registry.PAGE_RETRY_WAIT = original
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
