"""질문창 의미 검색(embeddings.py) 검수. 네트워크·DB를 쓰지 않는다 (결정 0019).

실행: uv run python -m tests.web.check_embeddings
"""
import os
import sys

import httpx

import embeddings

failed: list[str] = []


def check(name: str, ok: bool) -> None:
    print(("통과" if ok else "실패"), name)
    if not ok:
        failed.append(name)


class FakeResponse:
    def __init__(self, status: int, body: dict):
        self.status_code, self._body = status, body

    def json(self) -> dict:
        return self._body


def with_post(fake, call):
    original = httpx.post
    httpx.post = fake
    try:
        return call()
    finally:
        httpx.post = original


def ok_body(n: int, dim: int = embeddings.DIM) -> dict:
    return {"success": True, "errors": [], "result": {"data": [[0.1] * dim for _ in range(n)]}}


def raises_unavailable(call) -> bool:
    try:
        call()
    except embeddings.EmbeddingUnavailable:
        return True
    return False


def no_timeout(*a, **k):
    raise httpx.ReadTimeout("느림")


os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"] = "acc", "tok"
check("키가 있으면 켜짐", embeddings.enabled())
check("벡터 글자 모양", embeddings.vector_literal([0.5, -1.0, 0.25]) == "[0.5,-1,0.25]")
check("항목 글은 600자까지", len(embeddings.item_text("t" * 400, "s" * 400, "d" * 400)) == embeddings.TEXT_MAX)
check("항목 글은 빈 칸을 견딤", embeddings.item_text("제목", None, None).startswith("제목."))

check("정상 응답은 벡터 목록", len(with_post(lambda *a, **k: FakeResponse(200, ok_body(2)), lambda: embeddings.embed(["a", "b"]))) == 2)
check("한도 초과(429)는 쓸 수 없음 처리", raises_unavailable(lambda: with_post(
    lambda *a, **k: FakeResponse(429, {"success": False, "errors": [{"message": "limit"}]}), lambda: embeddings.embed(["a"]))))
check("차원이 다르면 쓸 수 없음 처리", raises_unavailable(lambda: with_post(lambda *a, **k: FakeResponse(200, ok_body(1, 8)), lambda: embeddings.embed(["a"]))))
check("시간 초과는 쓸 수 없음 처리", raises_unavailable(lambda: with_post(no_timeout, lambda: embeddings.embed(["a"]))))
check("개수가 안 맞으면 쓸 수 없음 처리", raises_unavailable(lambda: with_post(lambda *a, **k: FakeResponse(200, ok_body(1)), lambda: embeddings.embed(["a", "b"]))))
check("search는 호출 실패에도 빈 목록", with_post(no_timeout, lambda: embeddings.search("큐웬")) == [])

os.environ["CF_ACCOUNT_ID"] = ""
check("키가 없으면 꺼짐", not embeddings.enabled())
check("키가 없으면 search는 빈 목록", embeddings.search("큐웬") == [])
check("키가 없으면 embed_missing은 0", embeddings.embed_missing() == 0)
check("키가 없으면 embed는 쓸 수 없음", raises_unavailable(lambda: embeddings.embed(["a"])))

check("fuse: 한쪽이 비면 다른 쪽 순서 그대로", sorted(embeddings.fuse([3, 1, 2], []), key=embeddings.fuse([3, 1, 2], []).get, reverse=True) == [3, 1, 2])
check("fuse: 의미 검색에만 있는 항목도 들어옴", 9 in embeddings.fuse([1, 2], [9, 1]))
merged = embeddings.fuse([1, 2, 3], [3, 9])
check("fuse: 양쪽에 있는 항목이 한쪽만 있는 항목보다 위", merged[3] > merged[2] and merged[3] > merged[9])

sys.exit(1 if failed else 0)
