"""항목 벡터를 만든다 (결정 0019). 운영 DB를 바꾸는 명령이라 사람이 직접 실행한다.

- uv run python -m pipeline.embed_items --init      : pgvector 확장·표·색인 만들기 (한 번)
- uv run python -m pipeline.embed_items --backfill  : 벡터 없는 항목을 모두 채우기 (--max N으로 상한)
- uv run python -m pipeline.embed_items --status    : 항목 수와 벡터 수
크론(pipeline/cron.tick)은 새 항목 벡터를 차례마다 조금씩 채운다.
"""
import argparse
import sys

from sqlalchemy import text

import config  # noqa: F401  (.env 읽기)
import db
import embeddings


def status() -> dict:
    with db.get_engine().connect() as conn:
        items = conn.execute(text("SELECT count(*) FROM items")).scalar()
        try:
            vectors = conn.execute(text("SELECT count(*) FROM item_embeddings")).scalar()
        except Exception:
            vectors = None
    return {"items": items, "vectors": vectors, "keys": "설정됨" if embeddings.enabled() else "비어있음"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--max", type=int, default=20000)
    args = parser.parse_args(argv)
    if args.init:
        embeddings.ensure_schema()
        print("pgvector 확장과 item_embeddings 표를 준비했다")
    if args.backfill:
        total = 0
        while total < args.max:
            done = embeddings.embed_missing(min(500, args.max - total))
            if not done:
                break
            total += done
            print(f"채운 수 {total}", flush=True)
    print(status())
    return 0


if __name__ == "__main__":
    sys.exit(main())
