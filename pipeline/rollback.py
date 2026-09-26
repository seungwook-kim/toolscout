"""에이전트 되돌림 두 개 (계획안 5장 "되돌림 두 개", 설계 원칙 14, 세션 8). 하루 실행(run_daily)이 부른다.

- 되돌림 1 (verify_failed): 사용자 후보 도구 중 검증관이 실패(설치 실패·원문 접근 불가)로 낸 항목은 큐레이터를 다시 불러
  "대체 항목 선택" 또는 "비움"을 판단하게 한다. 항목당 1회. 대체 후보는 오늘 선별된 도구 중 아직 안 고르고, 본 적 없고, 실패가 아닌 것
- 되돌림 2 (evidence_short): 해설가가 도구 카드의 근거(좋은 점·아쉬운 점 evidence_url)를 하나도 못 채우면 검증관에 재요청 1회
  (verifier.reverify) → 결과를 붙여 해설가를 한 번 더 부른다. 그래도 근거가 없으면 카드에 "확인 필요"
  재검증은 한 실행에서 항목당 1회(사용자끼리 결과 공유), 최대 EVIDENCE_ROLLBACK_MAX건. 넘으면 재검증 없이 "확인 필요"
- 되돌림마다 트레이스에 rollback:* 스팬이 남는다
"""
import asyncio

from agent import curator, explainer, tracing, verifier
from agent.structured import Stats
from pipeline import verification

TOOL_TYPES = ("mcp", "skill")
EVIDENCE_ROLLBACK_MAX = 5  # 한 실행의 재검증 상한 (E2B 재검증이 건당 1~2분이라 07:00~08:00 안에 끝나게)
CHECK_NEEDED = "확인 필요"


async def verify_failed(plan: dict, selected: list[dict], memory: dict, results: dict, stats: Stats, model_call=None) -> list[dict]:
    """plan의 tools·related를 고친다. 반환: 되돌림 기록 [{title, action, replacement?, why}]."""
    events = []
    chosen = {i["url"] for key in ("news", "tools", "related") for i in plan.get(key, [])}
    seen = set(memory.get("seen_urls", []))
    failed_urls = {url for url, r in results.items() if r.get("request_status") == "failed"}
    for key in ("tools", "related"):
        kept = []
        for item in plan.get(key, []):
            if item["url"] not in failed_urls:
                kept.append(item)
                continue
            failure = (results[item["url"]] or {}).get("note") or "검증 실패"
            candidates = [c for c in selected if c.get("type") in TOOL_TYPES and c["url"] not in chosen and c["url"] not in seen
                          and c["url"] not in failed_urls and memory.get("weights", {}).get(c.get("topic"), 0) > -5]
            with tracing.span("rollback:verify_failed", kind="chain",
                              input={"user_id": memory["user_id"], "failed": item["title"], "reason": failure, "candidates": len(candidates)}) as span:
                decision = await curator.replan_failed(item | {"verify_failure": failure}, candidates, memory, stats, model_call)
                span.update(output={"action": decision["action"], "why": decision["why"],
                                    "replacement": decision.get("item", {}).get("title")})
            event = {"title": item["title"], "reason": failure, "action": decision["action"], "why": decision["why"]}
            if decision["action"] == "replace":
                replacement = decision["item"] | {"why": decision["why"], "rank": item.get("rank"), "related": item.get("related", False)}
                kept.append(replacement)
                chosen.add(replacement["url"])
                event["replacement"] = replacement["title"]
            events.append(event)
        plan[key] = kept
    return events


def _has_evidence(card: dict) -> bool:
    return any(p.get("evidence_url") for p in (card.get("pros") or []) + (card.get("cons") or []))


async def evidence_short(explained: dict, items_by_url: dict[str, dict], memory: dict, client, stats: Stats, *, today,
                         model_call=None, reverify=None, load_results=None, reverified: dict | None = None) -> list[dict]:
    """explained["cards"]를 고친다. reverified는 실행 전체가 공유하는 {url: 재검증 결과}. reverify·load_results는 검수용 주입.
    반환: [{title, reverify_status, recovered}]."""
    reverify = reverify or (lambda item: verifier.reverify(item, today=today, model_call=model_call))
    load_results = load_results or (lambda urls: asyncio.to_thread(verification.results_for, urls))
    reverified = {} if reverified is None else reverified
    events, cards = [], []
    for card in explained["cards"]:
        if card.get("type") not in TOOL_TYPES or _has_evidence(card):
            cards.append(card)
            continue
        item = items_by_url[card["url"]]
        with tracing.span("rollback:evidence_short", kind="chain", input={"user_id": memory["user_id"], "title": card["title"]}) as span:
            recovered, outcome = False, reverified.get(card["url"])
            if outcome is None and len(reverified) < EVIDENCE_ROLLBACK_MAX:
                outcome = reverified[card["url"]] = await reverify(item)
            if outcome is not None:
                fresh = (await load_results([card["url"]])).get(card["url"]) or {}
                item = item | {"verification": fresh.get("verification"), "risk_signal": fresh.get("risk_signal")}
                items_by_url[card["url"]] = item
                redo = await explainer.explain_item(item, memory, client, stats, model_call,
                                                    feedback="근거 링크가 없어 검증관이 다시 확인했다. 검증 결과와 원문으로 좋은 점·아쉬운 점 근거를 채운다")
                recovered = redo["status"] == "card" and _has_evidence(redo["card"])
            if recovered:
                cards.append(redo["card"] | {"rank": card.get("rank")})
            else:
                notices = [n for n in (card.get("notice") or "").split(" · ") if n]
                cards.append(card | {"notice": " · ".join(dict.fromkeys(notices + [CHECK_NEEDED]))})
            status = outcome.get("status") if outcome else "skipped_limit"
            span.update(output={"reverify": status, "recovered": recovered})
        events.append({"title": card["title"], "reverify_status": status, "recovered": recovered})
    explained["cards"] = cards
    return events


NOT_REQUESTED = {"mcp": "검증 안 함", "skill": "판독 안 함"}


def attach(cards: list[dict], results: dict) -> list[dict]:
    """카드에 검증 결과 칸을 붙인다 (verification·risk_signal·verification_note).
    요청 행조차 없는 도구 카드는 "검증 안 함"으로 적는다. 비워 두면 메일·화면이 "검증 예정"으로 보여 사실과 달라진다."""
    out = []
    for card in cards:
        found = results.get(card["url"]) or {}
        note = found.get("note")
        if not found and card.get("type") in NOT_REQUESTED:
            note = NOT_REQUESTED[card["type"]]
        out.append(card | {"verification": found.get("verification") or card.get("verification"),
                           "risk_signal": found.get("risk_signal") or card.get("risk_signal"),
                           "verification_note": note})
    return out
