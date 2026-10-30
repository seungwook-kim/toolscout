"""항목 의미 검색 (결정 0019). Cloudflare Workers AI bge-m3로 벡터를 만들고 Supabase pgvector에서 찾는다.

- 키(CF_ACCOUNT_ID·CF_API_TOKEN)가 없거나 호출·DB가 실패하면 빈 결과를 돌려준다. 질문창은 키워드 검색으로 계속 동작한다
- 표 만들기(ensure_schema)는 자동으로 하지 않는다: `python -m pipeline.embed_items --init`을 직접 실행할 때만
- 무료 요금제는 하루 한도를 넘으면 청구 없이 오류로 멈춘다. 그날은 이 모듈이 빈 결과를 돌려주고 키워드 검색만 쓴다
- 새 라이브러리 없이 httpx로 REST를 부르고, 벡터는 `'[...]'` 글자로 SQL에 실어 CAST한다
"""
import logging
import os

import httpx
from sqlalchemy import text

import db
from agent import tracing

log = logging.getLogger("toolscout.embeddings")

MODEL = "@cf/baai/bge-m3"
DIM = 1024
BATCH = 100
TEXT_MAX = 600
QUERY_TIMEOUT = 8.0  # 질문 하나를 기다리는 시간. 넘으면 키워드 검색만 쓴다
BATCH_TIMEOUT = 120.0
RRF_K = 60


class EmbeddingUnavailable(Exception):
    """키 없음·호출 실패·한도 초과. 부르는 쪽은 키워드 검색으로 돌아간다."""


def enabled() -> bool:
    return bool(os.environ.get("CF_ACCOUNT_ID", "").strip() and os.environ.get("CF_API_TOKEN", "").strip())


def item_text(title: str | None, summary_ko: str | None, description: str | None) -> str:
    return f"{title or ''}. {summary_ko or ''} {description or ''}"[:TEXT_MAX]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6g}" for x in vector) + "]"


def embed(texts: list[str], timeout: float = BATCH_TIMEOUT) -> list[list[float]]:
    if not enabled():
        raise EmbeddingUnavailable("키 없음")
    url = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CF_ACCOUNT_ID'].strip()}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {os.environ['CF_API_TOKEN'].strip()}"}
    with tracing.span("embed", kind="embedding", model=MODEL, input={"texts": len(texts)}):
        try:
            response = httpx.post(url, headers=headers, json={"text": texts}, timeout=timeout)
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingUnavailable(type(exc).__name__) from exc
        data = (body.get("result") or {}).get("data")
        if response.status_code != 200 or not body.get("success") or not data or len(data) != len(texts):
            raise EmbeddingUnavailable(f"HTTP {response.status_code} {[e.get('message') for e in body.get('errors', [])][:1]}")
        if len(data[0]) != DIM:
            raise EmbeddingUnavailable(f"차원 {len(data[0])} (기대 {DIM})")
        return data


def fuse(lexical_ids: list[int], dense_ids: list[int]) -> dict[int, float]:
    """두 순위 목록을 합친 점수(RRF). 한쪽이 비어 있으면 다른 쪽 순서 그대로다."""
    score: dict[int, float] = {}
    for ranking in (lexical_ids, dense_ids):
        for rank, item_id in enumerate(ranking):
            score[item_id] = score.get(item_id, 0.0) + 1.0 / (RRF_K + rank)
    return score


def search(question: str, limit: int = 20) -> list[int]:
    """질문과 뜻이 가까운 항목 id (가까운 순). 어떤 실패든 빈 목록."""
    if not enabled():
        return []
    try:
        vector = embed([question], timeout=QUERY_TIMEOUT)[0]
        with db.get_engine().connect() as conn:
            rows = conn.execute(text("SELECT item_id FROM item_embeddings ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"),
                                {"v": vector_literal(vector), "n": limit}).all()
        return [r[0] for r in rows]
    except Exception as exc:  # 표가 아직 없거나 연결·한도 문제 모두 같은 처리
        log.warning("의미 검색을 건너뜀(%s)", type(exc).__name__)
        return []


def ensure_schema() -> None:
    """pgvector 확장과 표·색인 만들기. 운영 DB를 바꾸므로 사람이 명령으로 부를 때만 쓴다."""
    with db.get_engine().begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text(f"""CREATE TABLE IF NOT EXISTS item_embeddings (
            item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
            model VARCHAR NOT NULL,
            embedding vector({DIM}) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'))"""))
        conn.execute(text("CREATE INDEX IF NOT EXISTS item_embeddings_hnsw ON item_embeddings USING hnsw (embedding vector_cosine_ops)"))


def embed_missing(limit: int = 300) -> int:
    """벡터가 없는 항목을 최대 limit개 채운다. 반환: 채운 수. 표가 없거나 키가 없으면 0."""
    if not enabled():
        return 0
    try:
        with db.get_engine().connect() as conn:
            rows = conn.execute(text("""SELECT i.id, i.title, i.summary_ko, i.description FROM items i
                LEFT JOIN item_embeddings e ON e.item_id = i.id WHERE e.item_id IS NULL ORDER BY i.id DESC LIMIT :n"""), {"n": limit}).all()
        done = 0
        for start in range(0, len(rows), BATCH):
            chunk = rows[start:start + BATCH]
            vectors = embed([item_text(r.title, r.summary_ko, r.description) for r in chunk])
            with db.get_engine().begin() as conn:
                conn.execute(text("INSERT INTO item_embeddings (item_id, model, embedding) VALUES (:id, :m, CAST(:v AS vector)) ON CONFLICT DO NOTHING"),
                             [{"id": r.id, "m": MODEL, "v": vector_literal(v)} for r, v in zip(chunk, vectors)])
            done += len(chunk)
        return done
    except Exception as exc:
        log.warning("항목 벡터 채우기를 건너뜀(%s)", type(exc).__name__)
        return 0
