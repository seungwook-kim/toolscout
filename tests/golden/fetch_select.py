"""하루 실행의 선별 판정을 Langfuse 트레이스에서 꺼내 tests/golden/run_select_<날짜>.json으로 저장한다. 모델을 부르지 않는다.

실행: uv run python -m tests.golden.fetch_select --date 2026-09-27
- 그날 briefings의 trace_id(하루 실행 트레이스 하나)를 찾고, llm:curator 관측 중 선별 호출(시스템 프롬프트에 "judgments")의
  입력 묶음(<data>)과 출력 판정을 id로 맞춘다. 같은 제목이 재시도로 두 번 나오면 마지막 판정
- 저장은 제목·출처·판정만 (기사 요약·본문은 넣지 않는다, 작업 규칙 9)
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import httpx
from sqlalchemy import select

import config  # noqa: F401  .env를 os.environ에 채운다
import db

HERE = Path(__file__).parent
KEYS = ("type", "source", "title", "ai_related", "worth_today", "topic", "importance")


def trace_id_for(day: date) -> str | None:
    with db.get_engine().connect() as c:
        return c.execute(select(db.Briefing.trace_id).where(db.Briefing.date == day, db.Briefing.trace_id.is_not(None))
                         .order_by(db.Briefing.id)).scalar()


def observations(trace_id: str) -> list[dict]:
    host = (os.environ.get("LANGFUSE_BASE_URL") or os.environ["LANGFUSE_HOST"]).rstrip("/")
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    out, page = [], 1
    with httpx.Client(timeout=60, auth=auth) as client:
        while True:
            response = client.get(f"{host}/api/public/observations", params={"traceId": trace_id, "page": page, "limit": 100})
            response.raise_for_status()
            body = response.json()
            out += body["data"]
            if page >= body["meta"]["totalPages"]:
                return out
            page += 1


def judgments(obs: list[dict]) -> list[dict]:
    rows: dict[str, dict] = {}
    for o in sorted(obs, key=lambda o: o["startTime"]):
        if not o["name"].startswith("llm:curator"):
            continue
        messages = o["input"] if isinstance(o["input"], list) else json.loads(o["input"])
        if '"judgments"' not in messages[0]["content"]:
            continue
        batch = json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1]["content"], re.S).group(1))
        text = o["output"].get("text") if isinstance(o["output"], dict) else o["output"]
        found = re.search(r"\{.*\}", text or "", re.S)
        try:
            by_id = {j["id"]: j for j in json.loads(found.group(0))["judgments"]}
        except (AttributeError, ValueError, KeyError, TypeError):
            continue  # 형식 실패한 답은 재시도 답이 뒤에 온다
        for item in batch:
            rows[item["title"]] = {k: item.get(k) for k in ("type", "source", "title")} | {
                k: by_id.get(item["id"], {}).get(k) for k in ("ai_related", "worth_today", "topic", "importance")}
    return list(rows.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    day = parser.parse_args().date
    trace_id = trace_id_for(day)
    if not trace_id:
        print(json.dumps({"date": str(day), "error": "그날 briefings가 없다"}, ensure_ascii=False))
        return 1
    rows = judgments(observations(trace_id))
    path = HERE / f"run_select_{day}.json"
    path.write_text(json.dumps({"date": str(day), "trace_id": trace_id, "judgments": rows}, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(json.dumps({"date": str(day), "trace_id": trace_id, "judgments": len(rows),
                      "selected": sum(bool(r["ai_related"] and r["worth_today"]) for r in rows), "saved": path.name}, ensure_ascii=False))
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
