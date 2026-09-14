"""하루 실행 (계획안 9.2 W1, 부록 B 1~6). 수집 → 정리 → 중복 제거 → 큐레이터 → 해설가 → 검증 노드 → 저장.

- 발송은 다음 단계(이메일)다. 저장한 briefings.sent_at은 null로 남는다
- 개발 모드(DEV_MODE≠0)는 users.is_test 사용자만 처리한다 (작업 규칙 7). 운영 모드는 is_test가 아닌 사용자
- 오늘 이미 발송한 사용자는 건너뛰고, 미발송이면 다시 만든다 (재실행 멱등)
- 하루 실행 전체가 트레이스 하나다. 카드마다 그 trace_id가 붙는다
- 해설가는 MCP fetch_article로 원문을 읽으므로 앱 서버(/mcp)가 떠 있어야 한다
실행: uv run python -m pipeline.run_daily [--mcp-url http://127.0.0.1:8000/mcp]
"""
import argparse
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone

from sqlmodel import select

import db
import memory
import models
from agent import curator, explainer, loop, tracing
from agent.structured import Stats
from pipeline import persist, validate
from pipeline.dedupe import dedupe
from pipeline.normalize import normalize

KST = timezone(timedelta(hours=9))
TOKEN_KEYS = ("calls", "input_tokens", "output_tokens", "format_failures", "unrecovered")


def today_kst() -> date:
    return datetime.now(KST).date()


def target_user_ids() -> list[int]:
    if models.dev_mode():
        return memory.test_user_ids()
    with db.session() as s:
        return list(s.exec(select(db.User.id).where(db.User.is_test == False).order_by(db.User.id)))  # noqa: E712


def collect_items() -> tuple[list[dict], list[dict]]:
    from sources.collect import collect

    results = collect()
    failures = [{"source": r.name, "error": r.error} for r in results if r.error]
    return [item for r in results for item in r.items], failures


async def run(today: date | None = None, *, items: list[dict] | None = None, mcp_url: str = loop.DEFAULT_MCP_URL,
              model_call=None) -> dict:
    """반환: 사용자별 저장 결과와 합계. items·model_call은 검수용 주입 (없으면 실제 수집·실제 모델)."""
    today = today or today_kst()
    started = time.perf_counter()
    with tracing.span("W1:daily", kind="chain", input={"date": str(today), "dev_mode": models.dev_mode()}) as root:
        failures = []
        if items is None:
            items, failures = await asyncio.to_thread(collect_items)
        prepared = dedupe(normalize(items))
        sent = await asyncio.to_thread(persist.sent_user_ids, today)
        user_ids = [uid for uid in await asyncio.to_thread(target_user_ids) if uid not in sent]
        memories = []
        for uid in user_ids:
            mem = memory.read(uid, today)
            pending = persist.pending_urls(uid, today)
            memories.append(mem | {"seen_urls": [url for url in mem["seen_urls"] if url not in pending]})

        curated = await curator.run(prepared, memories, model_call=model_call) if memories else None
        stats, users = Stats(), []
        by_user = {m["user_id"]: m for m in memories}
        for plan in curated["plans"] if curated else []:
            mem = by_user[plan["user_id"]]
            items_by_url = {item["url"]: item for item in plan["news"] + plan["tools"]}
            async with AsyncExitStack() as stack:
                client, _ = await loop._connect(stack, ["fetch_article"], mcp_url, plan["user_id"])
                explained = await explainer.explain_user(plan, mem, client, stats, model_call)

                async def redo(item, feedback, mem=mem, client=client):
                    return await explainer.explain_item(item, mem, client, stats, model_call, feedback=feedback)

                checked = await validate.run_user(explained, items_by_url, redo)
            saved = await asyncio.to_thread(persist.save_user, plan["user_id"], today, checked["cards"], items_by_url)
            users.append({"user_id": plan["user_id"], "role": mem["profile"]["role"], "empty": plan["empty"],
                          "empty_reason": plan["empty_reason"], "planned": len(items_by_url), "cards": len(checked["cards"]),
                          "saved": saved, "rejected": checked["rejected"], "excluded": checked["excluded"],
                          "retried": checked["retried"], "format_failed": checked["format_failed"],
                          "titles": [c["title"] for c in checked["cards"]]})

        curator_stats = curated["stats"] if curated else asdict(Stats())
        explainer_stats = asdict(stats)
        report = {
            "date": str(today), "dev_mode": models.dev_mode(), "collected": len(items), "prepared": len(prepared),
            "source_failures": failures, "skipped_sent_users": sorted(sent),
            "selected": len(curated["selected"]) if curated else 0, "verify_requests": len(curated["verify"]) if curated else 0,
            "users": users,
            "totals": {"briefings": sum(1 for u in users if u["saved"]["saved"]), "cards": sum(u["saved"]["saved"] for u in users),
                       "rejected": sum(len(u["rejected"]) for u in users), "excluded": sum(len(u["excluded"]) for u in users),
                       **{k: curator_stats[k] + explainer_stats[k] for k in TOKEN_KEYS}},
            "failure_examples": curator_stats["failure_examples"] + explainer_stats["failure_examples"],
            "trace_id": root.trace_id,
        }
        report["seconds"] = round(time.perf_counter() - started, 1)
        root.update(output={k: v for k, v in report.items() if k not in ("users", "failure_examples")})
    report["trace_url"] = tracing.trace_url(root.trace_id)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="toolscout 하루 실행 (발송 전까지)")
    parser.add_argument("--mcp-url", default=loop.DEFAULT_MCP_URL)
    args = parser.parse_args()
    try:
        report = asyncio.run(run(mcp_url=args.mcp_url))
    finally:
        tracing.flush()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["totals"]["unrecovered"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
