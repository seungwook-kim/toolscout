"""하루 실행 (계획안 9.2 W1, 부록 B 1~6). 수집 → 정리 → 중복 제거 → 큐레이터 → 해설가 → 검증 노드 → 저장.

- 발송은 다음 단계(이메일)다. 저장한 briefings.sent_at은 null로 남는다
- 개발 모드(DEV_MODE≠0)는 users.is_test 사용자만 처리한다 (작업 규칙 7). 운영 모드는 is_test가 아닌 사용자
- 오늘 이미 발송한 사용자는 건너뛰고, 미발송이면 다시 만든다 (재실행 멱등)
- 하루 실행 전체가 트레이스 하나다. 카드마다 그 trace_id가 붙는다
- 해설가는 MCP fetch_article로 원문을 읽으므로 앱 서버(/mcp)가 떠 있어야 한다
- 모델 장애(제공자 전부 실패)는 사용자·카드 단위로 건너뛴다. 대상 사용자가 모두 실패하면 종료 코드 2
- 카드가 0건이면(비움·전부 반려·제외) briefings에 empty_reason 행을 남긴다. 모델 장애로 0건이면 남기지 않는다(재실행 대상)
- 개발 모드에서는 형식 실패 예시를 tests/pipeline/format_failures.json에 쌓는다 (프롬프트를 고치기 전에 예시부터 모은다)
실행: uv run python -m pipeline.run_daily [--users N] [--limit N] [--mcp-url URL]
  디버깅은 --users 1 --limit 40, 전량은 하루 1회
"""
import argparse
import asyncio
import json
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import select

import db
import memory
import models
from agent import curator, explainer, loop, tracing
from agent.structured import MAX_EXAMPLES, Stats
from pipeline import persist, validate
from pipeline.dedupe import SOURCE_TIER, dedupe
from pipeline.normalize import normalize

KST = timezone(timedelta(hours=9))
TOKEN_KEYS = ("calls", "input_tokens", "output_tokens", "format_failures", "unrecovered")
FORMAT_FAILURES = Path(__file__).resolve().parents[1] / "tests" / "pipeline" / "format_failures.json"
FORMAT_FAILURES_KEEP = 300
EXIT_ALL_USERS_FAILED = 2


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


def top_items(items: list[dict], limit: int | None) -> list[dict]:
    """큐레이터 입력 상위 N건. 뉴스·도구 비율을 유지하고, 뉴스는 공식 > 매체 > 커뮤니티·최신 순, 도구는 별 수 순."""
    if not limit or len(items) <= limit:
        return items
    news = sorted((i for i in items if i["type"] == "news"), key=lambda i: str(i.get("published_at") or ""), reverse=True)
    news.sort(key=lambda i: SOURCE_TIER.get(i["source"], 9))
    tools = sorted((i for i in items if i["type"] != "news"), key=lambda i: i.get("stars") or 0, reverse=True)
    news_count = min(len(news), round(limit * len(news) / len(items)))
    return news[:news_count] + tools[:limit - news_count]


def record_format_failures(examples: list[dict], today: date) -> int:
    """개발 모드 형식 실패 예시를 파일에 쌓는다. 운영 모드는 실제 사용자 텍스트가 섞일 수 있어 쓰지 않는다."""
    if not examples or not models.dev_mode():
        return 0
    try:
        existing = json.loads(FORMAT_FAILURES.read_text(encoding="utf-8")) if FORMAT_FAILURES.exists() else []
    except json.JSONDecodeError:
        existing = []
    at = datetime.now(KST).isoformat(timespec="seconds")
    rows = (existing + [{"at": at, "date": str(today), **e} for e in examples])[-FORMAT_FAILURES_KEEP:]
    FORMAT_FAILURES.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(examples)


def empty_reason(plan: dict, checked: dict) -> str:
    if plan["empty"]:
        return plan["empty_reason"] or "오늘 보여줄 항목이 없다"
    return (f"후보 {len(plan['news']) + len(plan['tools'])}건 모두 빠짐 (반려 {len(checked['rejected'])}, "
            f"검증 제외 {len(checked['excluded'])}, 형식 실패 {len(checked['format_failed'])})")


async def run(today: date | None = None, *, items: list[dict] | None = None, mcp_url: str = loop.DEFAULT_MCP_URL,
              model_call=None, users: int | None = None, limit: int | None = None) -> dict:
    """반환: 사용자별 저장 결과와 합계. items·model_call은 검수용 주입 (없으면 실제 수집·실제 모델)."""
    today = today or today_kst()
    started = time.perf_counter()
    calls_before = models.PROVIDER_CALLS.copy()
    failovers_before = models.FAILOVERS.copy()
    with tracing.span("W1:daily", kind="chain", input={"date": str(today), "dev_mode": models.dev_mode(),
                                                       "users": users, "limit": limit}) as root:
        failures = []
        if items is None:
            items, failures = await asyncio.to_thread(collect_items)
        prepared = dedupe(normalize(items))
        curator_input = top_items(prepared, limit)
        sent = await asyncio.to_thread(persist.sent_user_ids, today)
        user_ids = [uid for uid in await asyncio.to_thread(target_user_ids) if uid not in sent][:users or None]
        memories = []
        for uid in user_ids:
            mem = memory.read(uid, today)
            pending = persist.pending_urls(uid, today)
            memories.append(mem | {"seen_urls": [url for url in mem["seen_urls"] if url not in pending]})

        curated = await curator.run(curator_input, memories, model_call=model_call) if memories else None
        stats, results = Stats(), []
        by_user = {m["user_id"]: m for m in memories}
        for plan in curated["plans"] if curated else []:
            mem = by_user[plan["user_id"]]
            entry = {"user_id": plan["user_id"], "role": mem["profile"]["role"], "planned": len(plan["news"]) + len(plan["tools"])}
            if plan.get("failed"):
                results.append(entry | {"status": "model_failed", "reason": plan["failure_reason"], "cards": 0})
                continue
            items_by_url = {item["url"]: item for item in plan["news"] + plan["tools"]}
            checked = {"cards": [], "rejected": [], "excluded": [], "retried": 0, "format_failed": [], "model_failed": []}
            if items_by_url:
                async with AsyncExitStack() as stack:
                    client, _ = await loop._connect(stack, ["fetch_article"], mcp_url, plan["user_id"])
                    explained = await explainer.explain_user(plan, mem, client, stats, model_call)

                    async def redo(item, feedback, mem=mem, client=client):
                        return await explainer.explain_item(item, mem, client, stats, model_call, feedback=feedback)

                    checked = await validate.run_user(explained, items_by_url, redo)
            entry |= {"rejected": checked["rejected"], "excluded": checked["excluded"], "retried": checked["retried"],
                      "format_failed": checked["format_failed"], "model_failed": checked["model_failed"],
                      "titles": [c["title"] for c in checked["cards"]]}
            if not checked["cards"] and checked["model_failed"]:
                results.append(entry | {"status": "model_failed", "reason": "카드 해설 모델 장애", "cards": 0})
                continue
            reason = None if checked["cards"] else empty_reason(plan, checked)
            saved = await asyncio.to_thread(persist.save_user, plan["user_id"], today, checked["cards"], items_by_url,
                                            trace_id=root.trace_id, empty_reason=reason)
            results.append(entry | {"status": saved["status"], "cards": saved["saved"], "empty_reason": reason,
                                    "duplicates": saved["duplicates"]})

        curator_stats = curated["stats"] if curated else asdict(Stats())
        explainer_stats = asdict(stats)
        examples = curator_stats["failure_examples"] + explainer_stats["failure_examples"]
        failed_users = [r["user_id"] for r in results if r["status"] == "model_failed"]
        report = {
            "date": str(today), "dev_mode": models.dev_mode(), "options": {"users": users, "limit": limit},
            "collected": len(items), "prepared": len(prepared), "curator_input": len(curator_input),
            "source_failures": failures, "skipped_sent_users": sorted(sent),
            "selected": len(curated["selected"]) if curated else 0, "verify_requests": len(curated["verify"]) if curated else 0,
            "users": results,
            "totals": {"users": len(results), "briefings": sum(1 for r in results if r["status"] in ("saved", "empty")),
                       "empty_users": sum(1 for r in results if r["status"] == "empty"),
                       "failed_users": len(failed_users), "cards": sum(r["cards"] for r in results),
                       "rejected": sum(len(r.get("rejected", [])) for r in results),
                       "excluded": sum(len(r.get("excluded", [])) for r in results),
                       **{k: curator_stats[k] + explainer_stats[k] for k in TOKEN_KEYS}},
            "all_users_failed": bool(results) and len(failed_users) == len(results),
            "providers": dict(models.PROVIDER_CALLS - calls_before),
            "failovers": dict(models.FAILOVERS - failovers_before),
            "model_failures": curator_stats["model_failures"] + explainer_stats["model_failures"],
            "failure_examples": examples[:MAX_EXAMPLES],
            "format_failures_recorded": record_format_failures(examples, today),
            "trace_id": root.trace_id,
        }
        report["seconds"] = round(time.perf_counter() - started, 1)
        root.update(output={k: v for k, v in report.items() if k not in ("users", "failure_examples")},
                    level="ERROR" if report["all_users_failed"] else "DEFAULT")
    report["trace_url"] = tracing.trace_url(root.trace_id)
    return report


def exit_code(report: dict) -> int:
    return EXIT_ALL_USERS_FAILED if report["all_users_failed"] else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="toolscout 하루 실행 (발송 전까지)")
    parser.add_argument("--users", type=int, default=None, help="처리할 사용자 수 (디버깅 1)")
    parser.add_argument("--limit", type=int, default=None, help="큐레이터 입력 상위 N건 (디버깅 40)")
    parser.add_argument("--mcp-url", default=loop.DEFAULT_MCP_URL)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        report = asyncio.run(run(mcp_url=args.mcp_url, users=args.users, limit=args.limit))
    finally:
        tracing.flush()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
