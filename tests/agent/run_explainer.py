"""해설가 검수 (계획안 5장 해설가, 부록 B 4, 카드 규격 9.3).

실행
- uv run python -m tests.agent.run_explainer --fake : 가짜 모델로 코드 경로 확인 (무료 한도를 쓰지 않음)
- uv run python -m tests.agent.run_explainer        : 큐레이터 결과 + 가짜 프로필 2개로 실제 카드, 같은 항목 for_me 3쌍 비교
결과: tests/agent/explainer_report.json (실제 모드, 제목·요약·for_me·숫자만)
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

from langchain_core.messages import AIMessage

import memory
from agent import explainer, schemas, tracing
from tests.app.check_main import KEY, free_port, start

HERE = Path(__file__).parent
CURATOR_RESULT = Path(tempfile.gettempdir()) / "toolscout_curator_result.json"
EXPLAINER_RESULT = Path(tempfile.gettempdir()) / "toolscout_explainer_result.json"
PAIRS = 3


def payload_of(messages) -> dict:
    match = re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S)
    return json.loads(match.group(1))


def fake_model():
    """항목 제목에 따라 정상 카드·반려·첫 응답 형식 오류를 돌려주는 가짜 해설가."""
    seen: set[str] = set()

    def call(role, messages, tools=None):
        item = payload_of(messages)["item"]
        if "REJECT" in item["title"]:
            return AIMessage('{"reject": true, "reject_reason": "마케터 프로필과 이어지는 쓰임이 없다"}')
        if "BROKEN" in item["title"] and item["title"] not in seen:
            seen.add(item["title"])
            return AIMessage('{"summary_ko": "끊긴 응답')
        body = {"summary_ko": "테스트 요약입니다.", "for_me": "사내 브리핑 봇에 붙여 볼 수 있다.",
                "pros": [{"text": "설치가 쉽다", "evidence_url": item["url"]}], "cons": [], "install_cmd": "npx -y example"}
        return AIMessage(json.dumps(body, ensure_ascii=False))
    return call


def item(title: str, url: str, kind: str = "news") -> dict:
    return {"title": title, "url": url, "type": kind, "source": "test", "summary": "테스트 항목", "why": "테스트 이유", "rank": 1}


async def fake_checks(mcp_url: str) -> dict:
    memories = [memory.read(uid) for uid in memory.test_user_ids()]
    plan = {"user_id": memories[0]["user_id"], "news": [item("뉴스 원문 못 읽음", "https://example.com/post"),
                                                      item("BROKEN 형식 오류 후 복구", "https://github.com/modelcontextprotocol/python-sdk")],
            "tools": [item("도구 원문 읽음", "https://github.com/modelcontextprotocol/python-sdk", "mcp"),
                      item("REJECT 반려 대상", "https://github.com/modelcontextprotocol/servers", "mcp")]}
    with tracing.span("test:explainer-fake", kind="chain"):
        result = await explainer.run([plan], memories[:1], mcp_url, model_call=fake_model())
    user = result["users"][0]
    cards = {c["title"]: c for c in user["cards"]}
    try:
        await explainer.explain_user(plan, memories[0] | {"is_test": False}, None, explainer.Stats(), fake_model())
        guard = False
    except PermissionError:
        guard = True
    return {
        "cards": len(user["cards"]), "rejected": user["rejected"], "stats": result["stats"],
        "checks": {
            "카드_규격_유효": all(schemas.Card.model_validate(c) for c in user["cards"]) and len(user["cards"]) == 3,
            "원문_읽음_표시": cards["도구 원문 읽음"]["source_checked"] is True and cards["도구 원문 읽음"]["notice"] is None,
            "원문_못읽음_원문확인필요": cards["뉴스 원문 못 읽음"]["notice"] == schemas.SOURCE_UNCHECKED,
            "반려_이유_기록": len(user["rejected"]) == 1 and bool(user["rejected"][0]["reason"]),
            "형식_실패_재시도_복구": result["stats"]["format_failures"] == 1 and result["stats"]["unrecovered"] == 0,
            "카드마다_trace_id": all(c["trace_id"] for c in user["cards"]),
            "뉴스는_install_cmd_없음": cards["뉴스 원문 못 읽음"]["install_cmd"] is None and bool(cards["도구 원문 읽음"]["install_cmd"]),
            "개발모드_is_test_아니면_거부": guard,
        },
    }


def comparison_plans(plans: list[dict]) -> list[dict]:
    """같은 항목을 두 사용자 모두에게 해설시키는 비교용 계획. 겹치는 항목이 모자라면 첫 사용자 후보에서 채운다."""
    a, b = plans[0], plans[1]
    urls_b = {i["url"] for i in b["news"] + b["tools"]}
    shared = [i for i in a["news"] + a["tools"] if i["url"] in urls_b][:PAIRS]
    extra = [i for i in a["news"] + a["tools"] if i["url"] not in urls_b][:PAIRS - len(shared)]
    compare = [{**i, "why": "같은 항목의 for_me 비교용"} for i in extra]
    return [{"user_id": b["user_id"], "news": [i for i in compare if i["type"] == "news"],
             "tools": [i for i in compare if i["type"] != "news"]}], shared + extra


async def live(mcp_url: str) -> dict:
    curated = json.loads(CURATOR_RESULT.read_text(encoding="utf-8"))
    memories = {m["user_id"]: m for m in (memory.read(uid) for uid in memory.test_user_ids())}
    plans = curated["plans"]
    extra_plans, pair_items = comparison_plans(plans)
    with tracing.span("test:explainer", kind="chain") as root:
        result = await explainer.run(plans, list(memories.values()), mcp_url)
        compare = await explainer.run(extra_plans, list(memories.values()), mcp_url)
    EXPLAINER_RESULT.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    cards_by_user = {u["user_id"]: {c["url"]: c for c in u["cards"]} for u in result["users"]}
    for u in compare["users"]:
        cards_by_user[u["user_id"]].update({c["url"]: c for c in u["cards"]})
    a, b = plans[0]["user_id"], plans[1]["user_id"]
    pairs = [{"title": i["title"], "for_me": {memories[a]["profile"]["role"]: cards_by_user[a].get(i["url"], {}).get("for_me"),
                                              memories[b]["profile"]["role"]: cards_by_user[b].get(i["url"], {}).get("for_me")}}
             for i in pair_items]
    stats = {k: result["stats"][k] + compare["stats"][k] for k in ("calls", "input_tokens", "output_tokens", "format_failures", "unrecovered")}
    all_cards = [c for u in result["users"] for c in u["cards"]]
    return {
        "users": [{"user_id": u["user_id"], "role": memories[u["user_id"]]["profile"]["role"],
                   "cards": [{"title": c["title"], "summary_ko": c["summary_ko"], "for_me": c["for_me"], "notice": c["notice"]}
                             for c in u["cards"]], "rejected": u["rejected"], "format_failed": u["format_failed"]}
                  for u in result["users"]],
        "for_me_pairs": pairs, "stats": stats,
        "failure_examples": result["stats"]["failure_examples"] + compare["stats"]["failure_examples"],
        "trace_url": tracing.trace_url(root.trace_id),
        "checks": {
            "형식_재시도_후_실패_없음": stats["unrecovered"] == 0,
            "카드_규격_유효": all(schemas.Card.model_validate(c) for c in all_cards),
            "카드마다_trace_id": all(c["trace_id"] for c in all_cards),
            "반려면_이유_있음": all(r["reason"] for u in result["users"] for r in u["rejected"]),
            "같은_항목_for_me_다름": sum(1 for p in pairs if len(set(filter(None, p["for_me"].values()))) == 2) >= min(PAIRS, len(pairs)) > 0,
        },
    }


def main() -> int:
    os.environ["MCP_SERVICE_KEY"] = KEY
    port = free_port()
    proc = start(port)
    started = time.perf_counter()
    try:
        mcp_url = f"http://127.0.0.1:{port}/mcp"
        report = asyncio.run(fake_checks(mcp_url) if "--fake" in sys.argv else live(mcp_url))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        tracing.flush()
    report["seconds"] = round(time.perf_counter() - started, 1)
    report["pass"] = all(report["checks"].values())
    if "--fake" not in sys.argv:
        (HERE / "explainer_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
