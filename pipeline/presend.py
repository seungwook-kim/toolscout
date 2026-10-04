"""발송 전 검증. 카드로 나갈 스킬·MCP를 하루 실행 안에서 바로 확인해 그날 카드에 결과를 붙인다.

- 스킬(2026-09-23 사용자 결정): SKILL.md를 읽고 정규식과 모델 판단을 맞춰 본다. 몇 초면 끝난다
- MCP(2026-09-26 사용자 결정 "가장 정확도가 높은 쪽"): E2B에서 실제로 설치·실행해 본다. 건당 최대 약 150초라
  한 실행에 MCP_PROBE_LIMIT건, 전체 MCP_BUDGET_SECONDS 안에서만 새로 시작한다. 남은 것은 요청만 남아 다음 날 06:00 W1-a가 한다
- 전에는 검증 요청을 카드가 정해지기 전에 선별 통과 도구 전체에서 골라, 카드로 나간 MCP 24장 중 10장이 요청 없이
  "검증 예정"으로 나갔다 (9/16~9/26 발송분 점검)
- 이미 결과가 있는 것과 이번에 안 뽑힌 도구는 건너뛴다. 실패해도 브리핑은 나간다. 설치 실패는 되돌림 1이 대체·비움으로 처리한다
"""
import asyncio
import logging
import re
import time
from datetime import date

from agent import verifier
from pipeline import verification

log = logging.getLogger("toolscout.presend")
SKILL_REVIEW_LIMIT = 5  # 한 실행에서 그 자리 판독할 스킬 수. 스킬 카드는 하루 몇 장이라 넉넉하다
MCP_PROBE_LIMIT = 4  # 07:00 실행이 08:00 발송 전에 끝나도록 (설치 90초·실행 30초·도구 목록 30초)
MCP_BUDGET_SECONDS = 600
DONE_STATUSES = ("done", "failed", "rejected")


def planned(curated: dict, kind: str) -> dict[str, dict]:
    """사용자 순서대로 카드로 나갈 도구(관련 카드 포함). {url: item}."""
    out: dict[str, dict] = {}
    for plan in curated["plans"]:
        for item in plan["tools"] + plan.get("related", []):
            if item.get("type") == kind:
                out.setdefault(item["url"], item)
    return out


def _known(found: dict | None, kind: str) -> bool:
    if not found:
        return False
    if kind == "skill":
        return bool(found.get("risk_signal"))
    return bool(found.get("verification")) or found.get("request_status") in DONE_STATUSES


def _stale(item: dict, found: dict | None) -> bool:
    """레지스트리 버전 업 항목인데 실측은 예전 버전이면 다시 확인한다 (10/2 anymd 8.3.0 카드에 9/26 8.0.0 결과가 붙음)."""
    versions = [p["version"] for p in (item.get("install") or {}).get("packages") or [] if p.get("version")]
    command = (found or {}).get("probe_command") or ""
    return bool(versions and command) and not any(re.search(rf"[@=]{re.escape(v)}(\s|$)", command) for v in versions)


async def _requests(curated: dict, today: date, kind: str, reason: str) -> tuple[list[dict], int]:
    """아직 결과가 없는 카드 도구를 요청 표에 넣고 검증관 요청 모양으로. 반환: (요청, 건너뛴 수)."""
    tools = planned(curated, kind)
    if not tools:
        return [], 0
    known = await asyncio.to_thread(verification.results_for, list(tools))
    # 새 버전 카드(update_from)와 버전 업 항목은 예전 버전 결과가 있어도 다시 확인한다
    newer = {url for url, item in tools.items() if item.get("update_from") or (kind == "mcp" and _stale(item, known.get(url)))}
    todo = [item for url, item in tools.items() if url in newer or not _known(known.get(url), kind)]
    # 한 실행 한도(MCP 4건)에 밀리면 새 버전 카드에 예전 버전 결과가 붙는다. 새 버전부터 확인한다
    todo.sort(key=lambda item: item["url"] not in newer)
    if not todo:
        return [], len(tools)
    depth = "read" if kind == "skill" else "full"
    await asyncio.to_thread(verification.save_requests, today, [item | {"depth": depth, "verify_reason": reason} for item in todo])
    requests = []
    for item in todo:
        item_id = await asyncio.to_thread(verification.item_id_for, item["url"])
        if item_id is not None:
            requests.append({"item_id": item_id, "kind": kind, "depth": depth, "type": item.get("type"), "title": item["title"],
                             "url": item["url"], "description": item.get("summary") or item.get("description"),
                             "install": verification.install_info(item) or {}})
    return requests, len(tools) - len(todo)


async def review_skills_now(curated: dict, today: date, model_call, mcp_url: str) -> dict:
    """카드로 나갈 스킬을 발송 전에 판독한다. 반환: {asked, done, skipped}."""
    requests, skipped = await _requests(curated, today, "skill", "스킬 카드 발송 전 판독")
    requests = requests[:SKILL_REVIEW_LIMIT]
    if not requests:
        return {"asked": 0, "done": 0, "skipped": skipped}
    try:
        result = await verifier.run(requests, model_call=model_call, mcp_url=mcp_url)
    except Exception as exc:  # 판독이 막혀도 브리핑은 나간다
        log.warning("스킬 발송 전 판독 건너뜀 (%s)", type(exc).__name__)
        return {"asked": len(requests), "done": 0, "skipped": skipped, "error": type(exc).__name__}
    return {"asked": len(requests), "done": result["counts"].get("done", 0), "skipped": skipped,
            "trace_id": result.get("trace_id")}


async def probe_mcps_now(curated: dict, today: date, model_call, mcp_url: str, clock=time.monotonic) -> dict:
    """카드로 나갈 MCP를 발송 전에 설치해 본다. 한 건씩 돌리고 예산을 넘기면 새로 시작하지 않는다.
    반환: {asked, statuses, skipped, deferred, seconds}. deferred는 요청만 남기고 다음 날 06:00으로 넘긴 수."""
    requests, skipped = await _requests(curated, today, "mcp", "MCP 카드 발송 전 설치 검증")
    started, statuses = clock(), []
    for request in requests[:MCP_PROBE_LIMIT]:
        if clock() - started >= MCP_BUDGET_SECONDS:
            break
        try:
            result = await verifier.run([request], model_call=model_call, mcp_url=mcp_url)
            statuses.append(result["items"][0]["status"] if result["items"] else "incomplete")
        except Exception as exc:  # 한 건이 막혀도 나머지와 브리핑은 계속한다
            log.warning("MCP 발송 전 검증 건너뜀 %s (%s)", request["item_id"], type(exc).__name__)
            statuses.append("error")
    return {"asked": len(statuses), "statuses": statuses, "skipped": skipped, "deferred": len(requests) - len(statuses),
            "seconds": round(clock() - started, 1)}
