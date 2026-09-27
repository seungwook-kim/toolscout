"""되돌림 두 개 검수 (계획안 5장 "되돌림 두 개", 부록 D, 세션 8 5단계). 모델·재검증·검증 결과 읽기는 가짜, DB·E2B·MCP를 쓰지 않는다.

실행: uv run python -m tests.verify.check_rollback
- 되돌림 1: 검증 실패 도구 → 큐레이터가 대체 선택(후보는 안 고른·안 본·실패 아닌·비선호 아닌 도구만) / 비움 / 모델 장애면 그 도구만 빠짐.
  실패 항목마다 판단 1회, 트레이스에 rollback:verify_failed
- 되돌림 2: 도구 카드 근거 없음 → 검증관 재요청 1회 → 결과를 붙여 해설가 다시 → 근거 채우면 교체, 그래도 없으면 "확인 필요".
  뉴스·근거 있는 카드는 안 건드림, 같은 링크는 사용자끼리 재검증 1회 공유, 상한을 넘으면 재검증 없이 "확인 필요", rollback:evidence_short
- attach: 카드에 verification·risk_signal·verification_note
"""
import asyncio
import json
import re
import sys
from contextlib import contextmanager

from langchain_core.messages import AIMessage

import models
from agent import tracing
from agent.structured import Stats
from pipeline import rollback

HOST = "https://example.test/rollback/"
KOREAN = {"summary_ko": "검수용 도구가 새 버전을 냈다. 설치가 짧아졌다.", "for_me": "사내 봇을 만들 때 참고할 수 있다.", "relevance": 4}
OUTAGE = models.ModelUnavailable("curator", ["groq 429", "gemini 429"])
state = {"replan": [], "explain": [], "reverify": [], "spans": [], "mode": "replace", "recover": True}


def tool(key: str, **extra) -> dict:
    return {"type": "mcp", "topic": "mcp_tools", "title": f"검수 {key}", "url": f"{HOST}{key}", "source": "mcp_registry",
            "summary": f"{key} 설명", "why": "검수용 선택 이유", **extra}


def fake_model(role, messages, tools=None, *, temperature=None):
    system = messages[0].content
    data = json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S).group(1))
    if "검증관 검증에서 실패했다" in system:
        state["replan"].append({"failed": data["failed"]["title"], "candidates": [c["title"] for c in data["candidates"]]})
        if state["mode"] == "outage":
            raise OUTAGE
        if state["mode"] == "replace" and data["candidates"]:
            body = {"action": "replace", "id": 1, "why": "같은 주제의 대체 도구"}
        else:
            body = {"action": "empty", "id": None, "why": "맞는 대체 후보가 없다"}
    else:
        retry = "근거 링크가 없어" in system
        state["explain"].append({"title": data["item"]["title"], "retry": retry, "verification": data.get("verification")})
        pros = [{"text": "설치 단계가 짧다", "evidence_url": data["item"]["url"]}] if retry and state["recover"] else []
        body = KOREAN | {"pros": pros}
    return AIMessage(json.dumps(body, ensure_ascii=False))


@contextmanager
def recording_span(name, **fields):
    state["spans"].append(name)
    with ORIGINAL_SPAN(name, **fields) as span:
        yield span


ORIGINAL_SPAN = tracing.span


async def fake_reverify(item):
    state["reverify"].append(item["url"])
    return {"status": "done", "item_id": 1}


async def fake_results(urls):
    chips = {"install": {"status": "ok", "label": "설치 성공"}, "tools_list": {"status": "ok", "label": "도구 3개"}}
    return {url: {"verification": chips, "risk_signal": None, "request_status": "done", "note": None} for url in urls}


def card(key: str, *, kind: str = "mcp", evidence: bool = False) -> dict:
    url = f"{HOST}{key}"
    return {"type": kind, "title": f"검수 {key}", "url": url, "summary_ko": "요약", "for_me": "쓸모", "why_this_card": "이유",
            "pros": [{"text": "근거 있음", "evidence_url": url}] if evidence else [], "cons": [], "notice": None, "rank": 1,
            "trace_id": "t", "source_checked": False}


MEMORY = {"user_id": 7, "is_test": True, "profile": {"role": "개발자", "free_text": None}, "seen_urls": [f"{HOST}seen"],
          "weights": {"mcp_tools": 1, "pricing": -6}}


async def rollback_one() -> dict:
    news = {"type": "news", "title": "검수 뉴스", "url": f"{HOST}news", "source": "rss", "why": "이유"}
    selected = [news, tool("broken"), tool("ok"), tool("seen"), tool("other_failed"), tool("disliked", topic="pricing"),
                tool("candidate")]
    results = {f"{HOST}broken": {"request_status": "failed", "note": "설치 실패"}, f"{HOST}ok": {"request_status": "done"},
               f"{HOST}other_failed": {"request_status": "failed", "note": "원문 접근 불가"}}

    def plan():
        return {"user_id": 7, "news": [news], "tools": [tool("broken", rank=2), tool("ok")], "related": []}

    out = {}
    for mode in ("replace", "empty", "outage"):
        state["mode"], before = mode, len(state["replan"])
        p, stats = plan(), Stats()
        events = await rollback.verify_failed(p, selected, MEMORY, results, stats, fake_model)
        out[mode] = {"tools": [t["title"] for t in p["tools"]], "events": events, "calls": state["replan"][before:],
                     "first": p["tools"][0]}
    none_failed = plan()
    state["mode"], before = "replace", len(state["replan"])
    quiet = await rollback.verify_failed(none_failed, selected, MEMORY, {f"{HOST}ok": {"request_status": "done"}}, Stats(), fake_model)
    out["quiet"] = {"events": quiet, "calls": len(state["replan"]) - before, "tools": [t["title"] for t in none_failed["tools"]]}
    return out


async def rollback_two() -> dict:
    items = {c["url"]: tool(c["title"].replace("검수 ", "")) for c in (card("no_evidence"), card("with_evidence"))}
    items[f"{HOST}news_plain"] = {"type": "news", "title": "검수 news_plain", "url": f"{HOST}news_plain", "source": "rss", "why": "이유"}

    async def run(cards, *, recover=True, shared=None):
        state["recover"] = recover
        explained = {"cards": cards}
        events = await rollback.evidence_short(explained, dict(items), MEMORY, None, Stats(), today=None, model_call=fake_model,
                                               reverify=fake_reverify, load_results=fake_results, reverified=shared)
        return explained["cards"], events

    out = {}
    before = len(state["explain"])
    cards, events = await run([card("news_plain", kind="news"), card("no_evidence"), card("with_evidence", evidence=True)])
    out["recovered"] = {"cards": cards, "events": events, "reverify": list(state["reverify"]), "explain": state["explain"][before:]}

    state["reverify"].clear()
    cards, events = await run([card("no_evidence")], recover=False)
    out["still_short"] = {"cards": cards, "events": events, "reverify": list(state["reverify"])}

    state["reverify"].clear()
    shared = {}
    await run([card("no_evidence")], recover=False, shared=shared)
    await run([card("no_evidence")], recover=False, shared=shared)  # 다른 사용자가 같은 도구를 받은 경우
    out["shared"] = {"reverify": list(state["reverify"]), "keys": list(shared)}

    state["reverify"].clear()
    full = {f"{HOST}filled/{n}": {"status": "done"} for n in range(rollback.EVIDENCE_ROLLBACK_MAX)}
    cards, events = await run([card("no_evidence")], shared=full)
    out["limit"] = {"cards": cards, "events": events, "reverify": list(state["reverify"])}
    return out


def main() -> int:
    tracing.span = recording_span
    try:
        one = asyncio.run(rollback_one())
        two = asyncio.run(rollback_two())
    finally:
        tracing.span = ORIGINAL_SPAN
    attached = rollback.attach([card("ok"), card("broken")], {
        f"{HOST}ok": {"verification": {"install": {"status": "ok", "label": "설치 성공"}}, "risk_signal": None, "note": None},
        f"{HOST}broken": {"verification": None, "risk_signal": None, "note": "설치 실패"}})
    rec, short, limit = two["recovered"], two["still_short"], two["limit"]
    notices = lambda c: [n for n in (c.get("notice") or "").split(" · ") if n]  # noqa: E731  "원문 확인 필요"와 구분
    checks = {
        "되돌림1_실패도구를_대체항목으로": one["replace"]["tools"] == ["검수 candidate", "검수 ok"]
        and one["replace"]["events"][0]["action"] == "replace" and one["replace"]["events"][0]["replacement"] == "검수 candidate"
        and one["replace"]["first"]["rank"] == 2 and one["replace"]["first"]["pick_why"] == "같은 주제의 대체 도구",
        "되돌림1_카드_이유에_교체사정_안나감": "대체" not in one["replace"]["first"]["why"] and bool(one["replace"]["first"]["why"]),
        "되돌림1_후보는_안고른·안본·실패아닌·비선호아닌_도구만": one["replace"]["calls"][0]["candidates"] == ["검수 candidate"],
        "되돌림1_실패이유를_큐레이터에_전달": one["replace"]["events"][0]["reason"] == "설치 실패",
        "되돌림1_비움_판단이면_빈자리": one["empty"]["tools"] == ["검수 ok"] and one["empty"]["events"][0]["action"] == "empty",
        "되돌림1_모델장애면_그도구만_빠짐": one["outage"]["tools"] == ["검수 ok"] and one["outage"]["events"][0]["action"] == "failed",
        "되돌림1_항목당_판단_1회": all(len(one[m]["calls"]) == 1 for m in ("replace", "empty", "outage")),
        "실패없으면_되돌림1_안함": one["quiet"]["events"] == [] and one["quiet"]["calls"] == 0,
        "되돌림2_근거없는_도구카드만_재검증_1회": rec["reverify"] == [f"{HOST}no_evidence"] and len(rec["events"]) == 1,
        "되돌림2_검증결과를_붙여_해설가_다시": any(e["retry"] and e["verification"] for e in rec["explain"]),
        "되돌림2_근거_채우면_카드_교체": rec["cards"][1]["pros"] and rec["events"][0]["recovered"]
        and rollback.CHECK_NEEDED not in notices(rec["cards"][1]),
        "뉴스·근거있는_카드는_그대로": rec["cards"][0] == card("news_plain", kind="news") and rec["cards"][2] == card("with_evidence", evidence=True),
        "되돌림2_그래도_부족하면_확인필요": notices(short["cards"][0]) == [rollback.CHECK_NEEDED] and short["events"][0]["recovered"] is False
        and short["reverify"] == [f"{HOST}no_evidence"],
        "같은링크_재검증은_사용자끼리_1회": two["shared"]["reverify"] == [f"{HOST}no_evidence"],
        "재검증_상한_넘으면_바로_확인필요": limit["reverify"] == [] and notices(limit["cards"][0]) == [rollback.CHECK_NEEDED]
        and limit["events"][0]["reverify_status"] == "skipped_limit",
        "트레이스에_되돌림_스팬": state["spans"].count("rollback:verify_failed") == 3 and "rollback:evidence_short" in state["spans"],
        "attach_검증칸·메모": attached[0]["verification"]["install"]["label"] == "설치 성공" and attached[1]["verification_note"] == "설치 실패",
    }
    report = {"rollback_1": {m: {"tools": one[m]["tools"], "events": one[m]["events"]} for m in ("replace", "empty", "outage")},
              "rollback_2": {k: two[k]["events"] for k in ("recovered", "still_short", "limit")}, "checks": checks,
              "pass": all(bool(v) for v in checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
