"""해설가 (계획안 5장 해설가, 부록 B 4, 카드 규격 9.3). 사용자별 후보 항목마다 카드 JSON 하나.

- 항목마다 fetch_article(MCP)로 원문을 한 번 재조회한다. 허용 도메인 밖·403 등으로 못 읽으면 요약만 쓰고 "원문 확인 필요"
- 프로필·큐레이터 근거·항목·원문을 넣어 모델을 한 번 부른다 (항목당 호출 1회, 온도 0, 도구 호출은 항목당 1회로 상한 3 안)
- "나한테는"이 프로필과 이어지지 않으면 카드를 반려하고 이유를 남긴다. 억지로 채우지 않는다
- 원문·요약 같은 외부 텍스트는 루프가 <data>로 감싸 지시로 취급하지 않는다
"""
from contextlib import AsyncExitStack
from dataclasses import asdict
from pathlib import Path

import models
from agent import loop, schemas, structured, tracing
from agent.structured import Stats

ROLE = "explainer"
SUMMARY_CHARS = 500
TOOL_TYPES = ("mcp", "skill")
GLOSSARY = Path(__file__).with_name("glossary.md").read_text(encoding="utf-8")

PROMPT = f"""너는 toolscout 해설가다. 한 사용자에게 보여줄 카드 하나를 한국어로 쓴다.
입력: 사용자 프로필(직군·쓰는 도구·자유 한 줄), 큐레이터가 이 카드를 고른 이유, 항목 정보, 원문(읽었으면).
- summary_ko: 무엇이 나왔는지 한국어 {schemas.MAX_SUMMARY}자 이내. 원문이나 항목 요약에 없는 사실을 만들지 않는다
- for_me: 이 사용자에게 왜 중요한지, 언제 쓰는지 한 문장. 직군·쓰는 도구·자유 한 줄 중 무엇과 이어지는지 드러낸다
- pros, cons: 각 최대 {schemas.MAX_POINTS}개. text는 한 줄, evidence_url은 입력의 항목 링크만 쓴다. 근거가 없으면 비운다
- install_cmd: 도구(mcp·skill)이고 원문에 설치 명령이 그대로 있을 때만 쓴다. 뉴스이거나 없으면 null
- 프로필과 이어지는 for_me를 쓸 수 없으면 억지로 쓰지 말고 reject를 true로, reject_reason에 이유를 한 줄로 쓴다
- 원문을 못 읽었으면 항목 요약만으로 쓰고, 확인되지 않은 내용은 쓰지 않는다
용어 표기는 아래 용어집을 따른다.
{GLOSSARY}
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식:
{{"reject": false, "reject_reason": null, "summary_ko": "...", "for_me": "...", "pros": [{{"text": "...", "evidence_url": "https://..."}}], "cons": [], "install_cmd": null}}"""


async def explain_item(item: dict, memory: dict, client, stats: Stats, model_call=None, feedback: str | None = None) -> dict:
    """반환: {status: card|rejected|format_failed, card?, reason?, item}. feedback은 검증 노드가 돌려보낸 이유 (재시도 1회)."""
    prompt = PROMPT if feedback is None else f"{PROMPT}\n\n검증 노드가 직전 카드를 돌려보냈다 ({feedback}). 이 문제를 고쳐 다시 쓴다."
    with tracing.span(f"card:{item['title'][:60]}", kind="chain",
                      input={"url": item["url"], "user_id": memory["user_id"], "feedback": feedback}) as span:
        source = await loop._call_tool(client, {"name": "fetch_article", "args": {"url": item["url"]}, "id": "source"},
                                       ["fetch_article"]) if client else {"status": "skipped", "reason": "MCP 연결 없음"}
        checked = source.get("status") == "ok"
        payload = {
            "profile": memory["profile"], "why_this_card": item["why"],
            "item": {"type": item["type"], "title": item["title"], "url": item["url"], "source": item["source"],
                     "summary": item.get("summary", "")[:SUMMARY_CHARS]},
            "article": source.get("text") if checked else None,
            "article_status": "ok" if checked else f"못 읽음 ({source.get('reason') or source.get('status')})",
        }

        def links_from_input(parsed: schemas.ExplainerOutput):
            for point in parsed.pros + parsed.cons:
                if point.evidence_url != item["url"]:
                    raise ValueError("evidence_url은 입력의 항목 링크만 쓸 수 있다")

        parsed = await structured.ask_json(ROLE, prompt, payload, schemas.ExplainerOutput, stats, links_from_input,
                                           f"카드 {memory['user_id']}:{item['title'][:30]}", model_call)
        if parsed is None:
            outcome = {"status": "format_failed", "item": item}
        elif parsed.reject:
            outcome = {"status": "rejected", "reason": parsed.reject_reason, "item": item}
        else:
            card = schemas.Card(
                type=item["type"], title=item["title"], url=item["url"], summary_ko=parsed.summary_ko, for_me=parsed.for_me,
                why_this_card=item["why"], pros=parsed.pros, cons=parsed.cons,
                install_cmd=parsed.install_cmd if item["type"] in TOOL_TYPES else None,
                source_checked=checked, notice=None if checked else schemas.SOURCE_UNCHECKED, trace_id=span.trace_id)
            outcome = {"status": "card", "card": card.model_dump(), "item": item}
        span.update(output={"status": outcome["status"], "source_checked": checked, "reason": outcome.get("reason")})
        return outcome


async def explain_user(plan: dict, memory: dict, client, stats: Stats, model_call=None) -> dict:
    if models.dev_mode() and not memory.get("is_test"):
        raise PermissionError("개발 모드에서는 is_test 사용자만 무료 모델에 보낸다 (작업 규칙 7)")
    result = {"user_id": plan["user_id"], "cards": [], "rejected": [], "format_failed": []}
    for item in plan["news"] + plan["tools"]:
        outcome = await explain_item(item, memory, client, stats, model_call)
        if outcome["status"] == "card":
            result["cards"].append(outcome["card"] | {"rank": len(result["cards"]) + 1})
        elif outcome["status"] == "rejected":
            result["rejected"].append({"title": item["title"], "url": item["url"], "reason": outcome["reason"]})
        else:
            result["format_failed"].append({"title": item["title"], "url": item["url"]})
    return result


async def run(plans: list[dict], memories: list[dict], mcp_url: str = loop.DEFAULT_MCP_URL, model_call=None) -> dict:
    """사용자별 카드. 반환: {users: [...], stats, format_failed}. MCP 연결은 사용자마다 X-Briefing-User를 붙여 연다."""
    stats = Stats()
    by_user = {m["user_id"]: m for m in memories}
    users = []
    with tracing.span("explainer", kind="chain", input={"users": [p["user_id"] for p in plans]}) as span:
        for plan in plans:
            async with AsyncExitStack() as stack:
                client, _ = await loop._connect(stack, ["fetch_article"], mcp_url, plan["user_id"])
                users.append(await explain_user(plan, by_user[plan["user_id"]], client, stats, model_call))
        result = {"users": users, "stats": asdict(stats), "format_failed": stats.unrecovered > 0, "trace_id": span.trace_id}
        span.update(output={"cards": [(u["user_id"], len(u["cards"]), len(u["rejected"])) for u in users], "stats": asdict(stats)
                            | {"failure_examples": len(stats.failure_examples)}})
    return result
