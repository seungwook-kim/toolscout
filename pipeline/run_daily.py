"""하루 실행 (계획안 9.2 W1, 부록 B 1~6). 수집 → 정리 → 중복 제거 → 큐레이터 → 해설가 → 검증 노드 → 저장.

- 발송은 다음 단계(이메일)다. 저장한 briefings.sent_at은 null로 남는다
- 개발 모드(DEV_MODE≠0)는 users.is_test 사용자만 처리한다 (작업 규칙 7). 운영 모드는 is_test가 아닌 사용자와 데모 프로필
- 어느 쪽이든 status가 approved인 사용자만 (초대제, 2026-09-16 사용자 결정)
- 오늘 이미 발송한 사용자는 건너뛰고, 미발송이면 다시 만든다 (재실행 멱등)
- 하루 실행 전체가 트레이스 하나다. 카드마다 그 trace_id가 붙는다
- 해설가는 MCP fetch_article로 원문을 읽으므로 앱 서버(/mcp)가 떠 있어야 한다
- 모델 장애(제공자 전부 실패)는 사용자·카드 단위로 건너뛴다. 대상 사용자가 모두 실패하면 종료 코드 2
- 카드가 0건이면(비움·전부 반려·제외) briefings에 empty_reason 행을 남긴다. 모델 장애로 0건이면 남기지 않는다(재실행 대상)
- 개발 모드에서는 형식 실패 예시를 tests/pipeline/format_failures.json에 쌓는다 (프롬프트를 고치기 전에 예시부터 모은다)
- 선별을 통과한 MCP·스킬은 카드가 아니어도 items에 쌓는다(관련 카드 후보). 저장이 실패해도 실행은 계속한다
- 월요일(KST)에는 사용자마다 관련 카드(F3-b)를 최대 3장 더 만든다. --related로 요일과 상관없이 켤 수 있다
- 검증(세션 8): 큐레이터 검증 요청을 verify_requests에 쌓고(06:00 W1-a가 처리), 사용자 후보마다 검증 결과를 읽어
  되돌림 1(실패 도구 대체·비움) → 해설 → 되돌림 2(근거 부족 재검증) → 검증 노드 → 카드에 verification·risk_signal
- 카드로 나갈 스킬·MCP는 이 실행 안에서 바로 판독·설치해 본다 (pipeline/presend.py, 스킬 9/23·MCP 9/26 사용자 결정)
실행: uv run python -m pipeline.run_daily [--users N] [--limit N] [--mcp-url URL]
  디버깅은 --users 1 --limit 40, 전량은 하루 1회
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_
from sqlmodel import select

import db
import memory
import models
from agent import curator, explainer, loop, tracing
from agent.structured import MAX_EXAMPLES, Stats
from pipeline import persist, presend, promo, rollback, tool_updates, validate, verification
from pipeline.dedupe import SOURCE_TIER, dedupe
from pipeline.normalize import normalize

log = logging.getLogger("toolscout.run_daily")
KST = timezone(timedelta(hours=9))
TOKEN_KEYS = ("calls", "input_tokens", "output_tokens", "format_failures", "unrecovered")
FORMAT_FAILURES = Path(__file__).resolve().parents[1] / "tests" / "pipeline" / "format_failures.json"
FORMAT_FAILURES_KEEP = 300
EXIT_ALL_USERS_FAILED = 2


def today_kst() -> date:
    return datetime.now(KST).date()


def target_user_ids() -> list[int]:
    """승인된 사용자만 (2026-09-16 초대제). 개발 모드는 is_test 프로필, 운영 모드는 실제 사용자 + 관리자.
    관리자(개발자 본인)는 개발 모드에서도 받도록 is_test로 둔 실제 계정이라 운영 모드(서버 배포, 2026-10-07)에서도 받는다.
    데모 프로필은 뺀다: /demo가 2026-10-08부터 고정 예시라 데모 브리핑을 만들 필요가 없다(모델 호출만 든다)."""
    with db.session() as s:
        query = select(db.User.id).where(db.User.status == "approved", db.User.is_demo == False)  # noqa: E712
        if models.dev_mode():
            query = query.where(db.User.is_test == True)  # noqa: E712
        else:
            query = query.where(or_(db.User.is_test == False, db.User.is_admin == True))  # noqa: E712
        return list(s.exec(query.order_by(db.User.id)))


def save_catalog(today: date, selected: list[dict]) -> int:
    try:
        return persist.save_catalog(today, selected)
    except Exception as exc:  # 도구 목록 쌓기는 부가 작업이라 브리핑을 막지 않는다
        log.warning("도구 목록 저장 건너뜀 (%s)", type(exc).__name__)
        return 0


def collect_items() -> tuple[list[dict], list[dict], dict]:
    """반환: (항목, 실패한 소스, MCP 저장소별 최신 버전)."""
    from sources.collect import collect

    results = collect()
    failures = [{"source": r.source, "error": r.error} for r in results if r.error]
    versions = {url: v for r in results for url, v in r.versions.items()}
    return [item for r in results for item in r.items], failures, versions


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
              model_call=None, users: int | None = None, limit: int | None = None, user_ids: list[int] | None = None,
              related: bool | None = None, tool_versions: dict | None = None) -> dict:
    """반환: 사용자별 저장 결과와 합계. items·model_call은 검수용 주입 (없으면 실제 수집·실제 모델). related가 None이면 월요일에만."""
    today = today or today_kst()
    with_related = related if related is not None else today.weekday() == 0
    started = time.perf_counter()
    calls_before = models.PROVIDER_CALLS.copy()
    failovers_before = models.FAILOVERS.copy()
    rate_limits_before = models.RATE_LIMITS.copy()
    with tracing.span("W1:daily", kind="chain", input={"date": str(today), "dev_mode": models.dev_mode(),
                                                       "users": users, "limit": limit}) as root:
        failures = []
        if items is None:
            items, failures, tool_versions = await asyncio.to_thread(collect_items)
        prepared, promo_dropped = promo.drop(dedupe(normalize(items)))  # 행사·책 홍보 연재는 모델에 보내기 전에 뺀다
        curator_input = top_items(prepared, limit)
        sent = await asyncio.to_thread(persist.sent_user_ids, today)
        allowed = await asyncio.to_thread(target_user_ids)
        wanted = [uid for uid in user_ids if uid in allowed] if user_ids is not None else allowed  # 설정 화면 "지금 만들기"는 본인만
        user_ids = [uid for uid in wanted if uid not in sent][:users or None]
        memories = []
        for uid in user_ids:
            mem = memory.read(uid, today)
            pending = persist.pending_urls(uid, today)
            memories.append(mem | {"seen_urls": [url for url in mem["seen_urls"] if url not in pending]})

        pools = {m["user_id"]: await asyncio.to_thread(persist.related_pool, m) for m in memories} if with_related else None
        curated = await curator.run(curator_input, memories, model_call=model_call, related_pools=pools) if memories else None
        catalog_saved = await asyncio.to_thread(save_catalog, today, curated["selected"]) if curated else 0
        verify_saved = await asyncio.to_thread(verification.save_requests, today, curated["verify"]) if curated else 0
        # 받아 본 MCP의 새 버전은 도구 칸 맨 앞에 (pipeline/tool_updates.py). 발송 전 검증이 새 버전을 다시 설치해 본다
        updates_added = await asyncio.to_thread(tool_updates.add_to_plans, curated["plans"], tool_versions or {}, today) if curated else 0
        # 카드로 나갈 스킬·MCP는 여기서 바로 확인해야 오늘 카드에 결과가 붙는다. 설치 실패는 아래 되돌림 1이 받는다
        skills_reviewed = await presend.review_skills_now(curated, today, model_call, mcp_url) if curated else {"asked": 0}
        mcps_probed = await presend.probe_mcps_now(curated, today, model_call, mcp_url) if curated else {"asked": 0}
        stats, results, reverified = Stats(), [], {}  # reverified: 되돌림 2 재검증 결과를 사용자끼리 공유 (항목당 1회)
        by_user = {m["user_id"]: m for m in memories}
        for plan in curated["plans"] if curated else []:
            mem = by_user[plan["user_id"]]
            entry = {"user_id": plan["user_id"], "role": mem["profile"]["role"], "planned": len(plan["news"]) + len(plan["tools"]),
                     "related_planned": len(plan.get("related", []))}
            if plan.get("failed"):
                results.append(entry | {"status": "model_failed", "reason": plan["failure_reason"], "cards": 0})
                continue
            tool_urls = [i["url"] for i in plan["tools"] + plan.get("related", [])]
            verified_before = await asyncio.to_thread(verification.results_for, tool_urls)
            rollback_failed = await rollback.verify_failed(plan, curated["selected"], mem, verified_before, stats, model_call)
            plan_tools = plan["tools"] + plan.get("related", [])
            verified = await asyncio.to_thread(verification.results_for, [i["url"] for i in plan_tools])
            for item in plan_tools:  # 해설가가 검증 결과를 읽고 쓰게
                item |= {k: (verified.get(item["url"]) or {}).get(k) for k in ("verification", "risk_signal")}
            items_by_url = {item["url"]: item for item in plan["news"] + plan_tools}
            checked = {"cards": [], "rejected": [], "excluded": [], "fixed": [], "retried": 0, "format_failed": [], "model_failed": []}
            rollback_evidence = []
            if items_by_url:
                async with AsyncExitStack() as stack:
                    client, _ = await loop._connect(stack, ["fetch_article"], mcp_url, plan["user_id"])
                    explained = await explainer.explain_user(plan, mem, client, stats, model_call)
                    rollback_evidence = await rollback.evidence_short(explained, items_by_url, mem, client, stats, today=today,
                                                                      model_call=model_call, reverified=reverified)

                    async def redo(item, feedback, mem=mem, client=client):
                        return await explainer.explain_item(item, mem, client, stats, model_call, feedback=feedback)

                    checked = await validate.run_user(explained, items_by_url, redo)
                final = await asyncio.to_thread(verification.results_for, [c["url"] for c in checked["cards"]])
                checked["cards"] = rollback.attach(checked["cards"], final)
            entry |= {"rejected": checked["rejected"], "excluded": checked["excluded"], "retried": checked["retried"], "fixed": checked.get("fixed", []),
                      "format_failed": checked["format_failed"], "model_failed": checked["model_failed"],
                      "titles": [c["title"] for c in checked["cards"]],
                      "related_titles": [c["title"] for c in checked["cards"] if c.get("related")],
                      "rollbacks": {"verify_failed": rollback_failed, "evidence_short": rollback_evidence}}
            if not checked["cards"] and checked["model_failed"]:
                results.append(entry | {"status": "model_failed", "reason": "카드 해설 모델 장애", "cards": 0})
                continue
            reason = None if checked["cards"] else empty_reason(plan, checked)
            tool_cards = [c for c in checked["cards"] if c["type"] in ("mcp", "skill")]
            run_stats = {"selected": len(curated["selected"]), "rejected": len(checked["rejected"]),
                         "excluded": len(checked["excluded"]) + len(checked["format_failed"]),
                         "verify_requested": len(tool_cards),
                         "verified": sum(1 for c in tool_cards if c.get("verification") or c.get("risk_signal")),
                         "rollbacks": len(rollback_failed) + len(rollback_evidence)}
            saved = await asyncio.to_thread(persist.save_user, plan["user_id"], today, checked["cards"], items_by_url,
                                            trace_id=root.trace_id, empty_reason=reason, pool_size=len(curator_input),
                                            run_stats=run_stats)
            results.append(entry | {"status": saved["status"], "cards": saved["saved"], "empty_reason": reason,
                                    "duplicates": saved["duplicates"]})

        curator_stats = curated["stats"] if curated else asdict(Stats())
        explainer_stats = asdict(stats)
        examples = curator_stats["failure_examples"] + explainer_stats["failure_examples"]
        failed_users = [r["user_id"] for r in results if r["status"] == "model_failed"]
        report = {
            "date": str(today), "dev_mode": models.dev_mode(), "options": {"users": users, "limit": limit},
            "collected": len(items), "prepared": len(prepared), "curator_input": len(curator_input),
            "source_failures": failures, "skipped_sent_users": sorted(sent), "catalog_saved": catalog_saved, "verify_saved": verify_saved, "skills_reviewed": skills_reviewed, "promo_dropped": promo_dropped, "tool_updates": updates_added,
            "mcps_probed": mcps_probed,
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
            "rate_limits_429": dict(models.RATE_LIMITS - rate_limits_before),
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
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="브리핑 날짜 (기본 오늘 KST). 검수용 날짜로 돌릴 때")
    parser.add_argument("--mcp-url", default=loop.DEFAULT_MCP_URL)
    parser.add_argument("--related", action="store_true", default=None, help="요일과 상관없이 관련 카드(F3-b)도 만든다")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        report = asyncio.run(run(args.date, mcp_url=args.mcp_url, users=args.users, limit=args.limit))
    finally:
        tracing.flush()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
