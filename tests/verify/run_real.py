"""검증관 실제 실행 (세션 8 7단계). 실제 모델·실제 E2B·실제 원문으로 검증 요청 N건(기본 5)을 돌려 단계별 성공률·시간·위험 신호 분포를 본다.

실행: uv run python -m tests.verify.run_real [--count 5] [--rerun]
- 후보: 도구 목록(선별 통과 MCP·스킬, items)에 오늘 새로 수집한 설치 정보(레지스트리 packages·remotes, SKILL.md 주소)를 링크로 붙인다
- 큐레이터가 실제 모델로 검증 요청을 고른다(curator.verification_requests). 모자라면 아직 없는 종류(스킬) 먼저, 다음은 별 수 순으로 채우고 표시한다
- --rerun: 이미 처리한 요청도 대기로 되돌려 다시 돌린다 (고친 뒤 같은 항목으로 시간을 비교할 때)
- --only 이름,이름: 큐레이터를 건너뛰고 이름이 들어간 항목만 (설치 단계 경로를 따로 잴 때). --out: 결과 파일 이름
- 요청을 전날 날짜로 저장한 뒤 06:00 W1-a와 같은 verifier.run으로 한 건씩 돌린다 (검수 서버는 예약을 끈 채 따로 띄운다)
- 결과: tests/verify/real_report.json. 이미 완료된 요청은 다시 돌리지 않는다(verify_requests 멱등)
"""
import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config  # noqa: F401

import httpx
from sqlalchemy import select, update

import db
import models
from agent import curator, tracing, verifier
from agent.structured import Stats
from pipeline import verification
from pipeline.normalize import normalize
from pipeline.run_daily import today_kst
from sources import anthropic_skills, mcp_registry
from tests.app.check_main import KEY, free_port, start

HERE = Path(__file__).parent
STAGES = ("install", "run", "tools_list")


def candidates() -> list[dict]:
    """도구 목록 항목 + 오늘 수집한 설치 정보. 설치 정보가 없어도 후보로 둔다(검증관이 README를 읽는다)."""
    since = datetime.now(timezone.utc) - timedelta(days=7)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        fresh = normalize(mcp_registry.fetch(since, client).items + anthropic_skills.fetch(since, client).items)
    extra = {item["url"]: item for item in fresh}
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Item.url, db.Item.type, db.Item.title, db.Item.description, db.Item.topic, db.Item.source, db.Item.stars)
                            .where(db.Item.type.in_(["mcp", "skill"]), db.Item.topic.is_not(None))).all()
    out = []
    for r in rows:
        item = {"url": r.url, "type": r.type, "title": r.title, "summary": r.description or "", "topic": r.topic, "source": r.source,
                "stars": r.stars}
        out.append(item | {k: extra[r.url][k] for k in ("install", "skill_url") if extra.get(r.url, {}).get(k)})
    return sorted(out, key=lambda i: -(i.get("stars") or 0))


def summarize(results: list[dict]) -> dict:
    mcp = [r for r in results if r["kind"] == "mcp"]
    stage_rate = {}
    for stage in STAGES:
        statuses = [((r.get("probe") or {}).get("stages") or {}).get(stage, {}).get("status") for r in mcp if r.get("probe")]
        applicable = [s for s in statuses if s and s != "해당없음"]
        stage_rate[stage] = {"성공": applicable.count("성공"), "대상": len(applicable), "해당없음": statuses.count("해당없음")}
    auth = Counter(((r.get("probe") or {}).get("stages") or {}).get("auth", {}).get("status") or "미실행" for r in mcp)
    seconds = [r["seconds"] for r in results]
    return {
        "requests": len(results), "status": dict(Counter(r["status"] for r in results)),
        "mcp_stage_success": stage_rate, "mcp_auth": dict(auth),
        "mcp_probe_seconds": [round(((r.get("probe") or {}).get("duration_ms") or 0) / 1000, 1) for r in mcp],
        "skill_read": dict(Counter("ok" if r.get("review") else r["status"] for r in results if r["kind"] == "skill")),
        "risk_signal": dict(Counter((r.get("review") or {}).get("risk_signal") for r in results if r["kind"] == "skill")),
        "seconds_total": round(sum(seconds), 1), "seconds_avg": round(sum(seconds) / len(seconds), 1) if seconds else 0,
        "seconds_max": max(seconds) if seconds else 0,
    }


async def main_async(count: int, mcp_url: str, rerun: bool = False, only: list[str] | None = None) -> dict:
    today = today_kst()
    pool = candidates()
    stats = Stats()
    if only:
        pool = [i for i in pool if any(name in i["title"] for name in only)]
        count = len(pool)
    picked = [] if only else await curator.verification_requests(pool, stats)
    picked_urls = {p["url"] for p in picked}
    covered = {p["type"] for p in picked}
    rest = sorted((i for i in pool if i["url"] not in picked_urls), key=lambda i: i["type"] in covered)  # 없는 종류 먼저, 같으면 별 수 순 유지
    filler = [i | {"depth": "read" if i["type"] == "skill" else "full", "verify_reason": "검수 보충(큐레이터 미선택)"}
              for i in rest][:max(0, count - len(picked))]
    requests = (picked + filler)[:count]
    saved = verification.save_requests(today - timedelta(days=1), requests)
    if rerun:
        with db.get_engine().begin() as conn:
            ids = select(db.Item.id).where(db.Item.url.in_([r["url"] for r in requests]))
            conn.execute(update(db.VerifyRequest).where(db.VerifyRequest.item_id.in_(ids))
                         .values(status="pending", attempts=0, requested_on=today - timedelta(days=1)))
    calls_before, failovers_before, limits_before = models.PROVIDER_CALLS.copy(), models.FAILOVERS.copy(), models.RATE_LIMITS.copy()
    due = [d for d in verification.due_requests(today, limit=50) if d["url"] in {r["url"] for r in requests}]
    results = []
    for request in due:
        started = time.perf_counter()
        outcome = (await verifier.run([request], day=today, mcp_url=mcp_url))["items"][0]
        results.append(outcome | {"seconds": round(time.perf_counter() - started, 1), "url": request["url"],
                                  "had_install_info": bool((request.get("install") or {}).get("install") or (request.get("install") or {}).get("skill_url")),
                                  "by_curator": request["url"] in picked_urls})
    return {
        "date": str(today), "dev_mode": models.dev_mode(), "pool": len(pool),
        "pool_with_install_info": sum(1 for i in pool if i.get("install") or i.get("skill_url")),
        "curator_picked": len(picked), "filled": len(filler), "saved_new": saved, "ran": len(results),
        "curator_stats": {k: v for k, v in stats.__dict__.items() if k != "failure_examples"},
        "verifier_providers": dict(models.PROVIDER_CALLS - calls_before), "failovers": dict(models.FAILOVERS - failovers_before),
        "rate_limits_429": dict(models.RATE_LIMITS - limits_before),
        "summary": summarize(results),
        "items": [{k: r.get(k) for k in ("title", "kind", "status", "reason", "seconds", "by_curator", "had_install_info", "trace_id")}
                  | {"stages": {s: v.get("status") for s, v in ((r.get("probe") or {}).get("stages") or {}).items()},
                     "requirements": (r.get("probe") or {}).get("requirements"), "plan": (r.get("plan") or {}).get("kind"),
                     "risk": (r.get("review") or {}).get("risk_signal"), "risk_quote": (r.get("review") or {}).get("risk_quote"),
                     "completeness": (r.get("review") or {}).get("completeness")}
                  for r in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--rerun", action="store_true")
    parser.add_argument("--only", default="", help="쉼표로 준 이름이 들어간 항목만 (큐레이터 건너뜀)")
    parser.add_argument("--out", default="real_report.json")
    args = parser.parse_args()
    os.environ["MCP_SERVICE_KEY"] = KEY
    port = free_port()
    proc = start(port)
    try:
        only = [name for name in args.only.split(",") if name]
        report = asyncio.run(main_async(args.count, f"http://127.0.0.1:{port}/mcp", args.rerun, only))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        tracing.flush()
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    (HERE / args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["ran"] else 1


if __name__ == "__main__":
    sys.exit(main())
