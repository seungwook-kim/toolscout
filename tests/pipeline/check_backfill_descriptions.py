"""pipeline/backfill_descriptions 검수. 네트워크·DB를 쓰지 않는다 (결정 0020).

실행: uv run python -m tests.pipeline.check_backfill_descriptions
"""
import sys

from pipeline import backfill_descriptions as bd

failed: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("통과" if ok else "실패"), name)
    if not ok:
        failed.append(name)


def server(repo_url: str | None, description: str | None) -> dict:
    return {"name": "x/y", "description": description, "repository": {"url": repo_url} if repo_url else {}}


found = bd.descriptions_from([
    server("https://github.com/a/tool.git", "  Run apps.  "),
    server("https://github.com/b/long", "x" * 500),
    server("https://github.com/c/empty", "   "),
    server(None, "저장소 없음"),
    server("https://gitlab.com/d/other", "깃허브 아님"),
    server("https://github.com/modelcontextprotocol/registry", "레지스트리 자체 저장소"),
])
check("저장소 주소를 키로 쓰고 앞뒤 공백을 지움", found.get("https://github.com/a/tool") == "Run apps.")
check("설명은 300자까지", len(found["https://github.com/b/long"]) == bd.MAX_LEN)
check("설명이 비면 건너뜀", "https://github.com/c/empty" not in found)
check("저장소가 없거나 깃허브가 아니거나 레지스트리 자체 저장소면 건너뜀", len(found) == 2)


class FakeResponse:
    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body


class FakeClient:
    def __init__(self):
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        if "cursor" not in params:
            return FakeResponse({"servers": [{"server": {"name": "a"}}, {"server": {"name": "b"}}], "metadata": {"nextCursor": "c1"}})
        return FakeResponse({"servers": [{"server": {"name": "c"}}], "metadata": {}})


client = FakeClient()
check("쪽을 끝까지 이어서 받음", [s["name"] for s in bd.fetch_servers(client)] == ["a", "b", "c"] and client.calls == 2)
sys.exit(1 if failed else 0)
