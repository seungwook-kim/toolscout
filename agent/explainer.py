"""해설가 (계획안 5장 해설가, 부록 B 4, 카드 규격 9.3). 사용자별 후보 항목마다 카드 JSON 하나.

- 항목마다 fetch_article(MCP)로 원문을 한 번 재조회한다. 항목에 외부 출처 링크(source_url)가 있으면 그 링크로 읽고,
  읽을 링크가 없다고 표시된 항목(skip_fetch, 예: 외부 링크 없는 긱뉴스)은 요약만 쓴다. 못 읽으면 "원문 확인 필요"
- 프로필·큐레이터 근거·항목·원문을 넣어 모델을 한 번 부른다 (항목당 호출 1회, 온도 0, 도구 호출은 항목당 1회로 상한 3 안)
- "나한테는"이 프로필과 이어지지 않으면 카드를 반려하고 이유를 남긴다. 억지로 채우지 않는다
- 관련도(relevance 1~5)가 3 미만이면 반려한다 (2026-09-15 사용자 결정)
- 요약 길이·빈 값은 초안 카드(DraftCard)로 넘기고 검증 노드가 처리한다 (문장 끝에서 자름, 이유를 돌려 1회 자가 수정)
- 원문·요약 같은 외부 텍스트는 루프가 <data>로 감싸 지시로 취급하지 않는다
- 모델 장애(제공자 전부 실패)면 그 카드만 건너뛰고 model_failed에 이유를 남긴다
프롬프트의 길이·빈 값 규칙은 tests/pipeline/format_failures.json 예시 4건(요약 120자 초과 2, 요약·for_me null 2)을 보고 넣었다.
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
- summary_ko: 무엇이 나왔는지 한국어 두 문장 이하, 공백 포함 {schemas.MAX_SUMMARY}자 이내. 길면 핵심 한 가지만 남긴다.
  원문이나 항목 요약에 없는 사실을 만들지 않는다
- for_me: 이 사용자에게 왜 중요한지, 언제 쓰는지 한 문장 {schemas.MAX_FOR_ME}자 이내. 직군·쓰는 도구·자유 한 줄 중 무엇과 이어지는지 드러낸다
- relevance: 이 항목이 이 사용자에게 얼마나 관련 있는지 1~5 정수. 5 바로 쓸 수 있음, 4 분명히 관련, 3 참고할 만함,
  2 이하는 억지로 이어 붙여야 하는 연결. 2 이하라면 for_me를 꾸며 내지 말고 그 점수를 그대로 쓴다
- pros, cons: 각 최대 {schemas.MAX_POINTS}개. text는 한 줄, evidence_url은 입력의 항목 링크만 쓴다. 근거가 없으면 비운다
- install_cmd: 도구(mcp·skill)이고 원문에 설치 명령이 그대로 있을 때만 쓴다. 뉴스이거나 없으면 null
- reject가 false면 summary_ko와 for_me는 반드시 내용이 있는 문자열이다. 빈 문자열이나 null로 두지 않는다
- 프로필과 이어지는 for_me를 쓸 수 없으면 억지로 쓰지 말고 reject를 true로, reject_reason에 이유를 한 줄로 쓴다
- 원문을 못 읽었으면 항목 요약만으로 쓰고, 확인되지 않은 내용은 쓰지 않는다
용어 표기는 아래 용어집을 따른다.
{GLOSSARY}
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식:
{{"reject": false, "reject_reason": null, "relevance": 4, "summary_ko": "...", "for_me": "...", "pros": [{{"text": "...", "evidence_url": "https://..."}}], "cons": [], "install_cmd": null}}"""


async def explain_item(item: dict, memory: dict, client, stats: Stats, model_call=None, feedback: str | None = None) -> dict:
    """반환: {status: card|rejected|format_failed|model_failed, card?, reason?, item}. feedback은 검증 노드가 돌려보낸 이유."""
    prompt = PROMPT if feedback is None else f"{PROMPT}\n\n검증 노드가 직전 카드를 돌려보냈다 ({feedback}). 이 문제를 고쳐 다시 쓴다."
    with tracing.span(f"card:{item['title'][:60]}", kind="chain",
                      input={"url": item["url"], "user_id": memory["user_id"], "feedback": feedback}) as span:
        read_url = item.get("source_url") or item["url"]
        if item.get("skip_fetch") and not item.get("source_url"):
            source = {"status": "skipped", "reason": "원문 링크 없음, 요약만"}
        elif client:
            source = await loop._call_tool(client, {"name": "fetch_article", "args": {"url": read_url}, "id": "source"},
                                           ["fetch_article"])
        else:
            source = {"status": "skipped", "reason": "MCP 연결 없음"}
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

        label = f"카드 {memory['user_id']}:{item['title'][:30]}"
        try:
            parsed = await structured.ask_json(ROLE, prompt, payload, schemas.ExplainerOutput, stats, links_from_input,
                                               label, model_call)
        except models.ModelUnavailable as exc:
            outcome = {"status": "model_failed", "reason": stats.model_failed(label, exc), "item": item}
            span.update(output={"status": outcome["status"], "reason": outcome["reason"]}, level="WARNING")
            return outcome
        if parsed is None:
            reason = next((e["error"] for e in reversed(stats.failure_examples) if e["label"] == label), "형식 실패")
            outcome = {"status": "format_failed", "reason": f"형식 실패 2회: {reason}", "item": item}
        elif parsed.reject:
            outcome = {"status": "rejected", "reason": parsed.reject_reason, "item": item}
        elif parsed.relevance is not None and parsed.relevance < schemas.MIN_RELEVANCE:
            outcome = {"status": "rejected", "item": item,
                       "reason": f"관련도 {parsed.relevance}/5 (기준 {schemas.MIN_RELEVANCE} 미만): {(parsed.for_me or '')[:80]}"}
        else:
            notices = [schemas.SOURCE_UNCHECKED] if not checked else []
            if item.get("collection_note"):
                notices.append(item["collection_note"])
            card = schemas.DraftCard(
                type=item["type"], title=item["title"], url=item["url"], summary_ko=parsed.summary_ko or "",
                for_me=parsed.for_me or "", why_this_card=item["why"], pros=parsed.pros, cons=parsed.cons,
                install_cmd=parsed.install_cmd if item["type"] in TOOL_TYPES else None, relevance=parsed.relevance,
                source_checked=checked, notice=" · ".join(notices) or None, trace_id=span.trace_id)
            outcome = {"status": "card", "card": card.model_dump(), "item": item}
        span.update(output={"status": outcome["status"], "source_checked": checked, "reason": outcome.get("reason"),
                            "relevance": parsed.relevance if parsed else None},
                    level="WARNING" if outcome["status"] == "format_failed" else "DEFAULT")
        return outcome


async def explain_user(plan: dict, memory: dict, client, stats: Stats, model_call=None) -> dict:
    if models.dev_mode() and not memory.get("is_test"):
        raise PermissionError("개발 모드에서는 is_test 사용자만 무료 모델에 보낸다 (작업 규칙 7)")
    result = {"user_id": plan["user_id"], "cards": [], "rejected": [], "format_failed": [], "model_failed": []}
    for item in plan["news"] + plan["tools"]:
        outcome = await explain_item(item, memory, client, stats, model_call)
        if outcome["status"] == "card":
            result["cards"].append(outcome["card"] | {"rank": len(result["cards"]) + 1})
        elif outcome["status"] == "rejected":
            result["rejected"].append({"title": item["title"], "url": item["url"], "reason": outcome["reason"]})
        elif outcome["status"] == "model_failed":
            result["model_failed"].append({"title": item["title"], "url": item["url"], "reason": outcome["reason"]})
        else:
            result["format_failed"].append({"title": item["title"], "url": item["url"], "reason": outcome.get("reason")})
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
