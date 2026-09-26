"""해설가 (계획안 5장 해설가, 부록 B 4, 카드 규격 9.3). 사용자별 후보 항목마다 카드 JSON 하나. 질문창 답변(부록 E)도 맡는다.

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
import json
from contextlib import AsyncExitStack
from dataclasses import asdict
from functools import partial
from pathlib import Path

import models
from agent import loop, schemas, structured, tracing
from agent.structured import Stats

ROLE = "explainer"
SUMMARY_CHARS = 500
SUMMARY_ONLY_CHARS = 1500  # 원문 링크가 없어 요약만 쓰는 항목(예: 긱뉴스)은 요약을 더 길게 넘긴다
TOOL_TYPES = ("mcp", "skill")
GLOSSARY = Path(__file__).with_name("glossary.md").read_text(encoding="utf-8")

PROMPT = f"""너는 toolscout 해설가다. 한 사용자에게 보여줄 카드 하나를 한국어로 쓴다.
입력: 사용자 프로필(직군·쓰는 도구·자유 한 줄), 큐레이터가 이 카드를 고른 이유, 항목 정보, 원문(읽었으면).
- summary_ko: 무엇이 나왔는지 한국어 두 문장 이하, 공백 포함 {schemas.MAX_SUMMARY}자 이내. 길면 핵심 한 가지만 남긴다.
  원문이나 항목 요약에 없는 사실을 만들지 않는다
- 문장(summary_ko·for_me)은 모두 "~합니다"체로 끝낸다. "~했다"·"~이다"로 끝내지 않는다
- for_me: 이 사용자에게 왜 중요한지 한 문장 {schemas.MAX_FOR_ME}자 이내. 직군·쓰는 도구·자유 한 줄 중 무엇과 이어지는지 드러낸다.
  당장 쓸 일이 없어도 이 직군이 알아둘 이유(흐름이 어디로 가는지, 선택지가 늘었는지, 무엇을 조심할지)가 있으면 그것을 쓴다.
  자유 한 줄에 적힌 지금 하는 일에 그대로 쓸 수 있어야만 쓸모 있는 것은 아니다
  읽는 사람에게 직접 말하듯 주어 없이 쓴다. "사용자가 ~하므로", "개발자님께서", "~하시는" 같은 3인칭·호칭은 쓰지 않는다
  (예: "Claude Code로 긴 작업을 돌릴 때 캐시 비용을 줄이는 방법으로 참고할 수 있습니다")
  프로필에 없는 관심사·회사·도구를 지어내지 않는다. why_this_card와 같은 말을 되풀이하지 않고 그다음 이야기를 쓴다
- relevance: 이 항목이 이 사용자에게 얼마나 관련 있는지 1~5 정수. 5 바로 쓸 수 있음, 4 분명히 관련,
  3 지금 쓰지는 않아도 이 직군이 알아둘 만함(업계 흐름·새 선택지·주의할 점), 2 이하는 억지로 이어 붙여야 하는 연결.
  2 이하라면 for_me를 꾸며 내지 말고 그 점수를 그대로 쓴다
- pros, cons: 각 최대 {schemas.MAX_POINTS}개. text는 명사형 한 줄(예: "캐시된 입력 토큰 최대 90% 할인"), evidence_url은 입력의 항목 링크만 쓴다.
  근거가 없으면 비운다. 뉴스는 발표된 모델·제품·정책 자체의 장점과 한계만 쓴다. "~을 파악할 수 있음" 같은 기사를 읽는 이점,
  기사·책 소개, 원문을 못 읽었다는 말은 장단점이 아니다. 그런 것밖에 없으면 비운다
- install_cmd: 도구(mcp·skill)이고 원문에 설치 명령이 그대로 있을 때만 쓴다. 뉴스이거나 없으면 null
- reject가 false면 summary_ko와 for_me는 반드시 내용이 있는 문자열이다. 빈 문자열이나 null로 두지 않는다
- 입력의 항목은 큐레이터가 이 사용자의 프로필을 보고 고른 것이다. 고른 이유가 납득되면 살린다.
  직군·쓰는 도구·자유 한 줄·관심 주제 어느 것과도 이어 볼 수 없을 때만 reject를 true로 하고 reject_reason에 이유를 한 줄로 쓴다
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
                     "summary": item.get("summary", "")[:SUMMARY_ONLY_CHARS if item.get("skip_fetch") else SUMMARY_CHARS]},
            "article": source.get("text") if checked else None,
            "verification": item.get("verification"), "risk_signal": item.get("risk_signal"),  # 검증관 결과가 있으면 (세션 8)
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
                source_checked=checked, notice=" · ".join(notices) or None, related=bool(item.get("related")),
                headline=bool(item.get("headline")), trace_id=span.trace_id)
            outcome = {"status": "card", "card": card.model_dump(), "item": item}
        span.update(output={"status": outcome["status"], "source_checked": checked, "reason": outcome.get("reason"),
                            "relevance": parsed.relevance if parsed else None},
                    level="WARNING" if outcome["status"] == "format_failed" else "DEFAULT")
        return outcome


async def explain_user(plan: dict, memory: dict, client, stats: Stats, model_call=None) -> dict:
    if models.dev_mode() and not memory.get("is_test"):
        raise PermissionError("개발 모드에서는 is_test 사용자만 무료 모델에 보낸다 (작업 규칙 7)")
    result = {"user_id": plan["user_id"], "cards": [], "rejected": [], "format_failed": [], "model_failed": []}
    for item in plan["news"] + plan["tools"] + plan.get("related", []):
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


ANSWER_TOOL_CALLS = 3  # 질문 답변의 도구 호출 상한 (부록 E)
ANSWER_MAX_STEPS = ANSWER_TOOL_CALLS + 2
ANSWER_PROMPT = f"""너는 toolscout 해설가다. 사용자가 AI 브리핑 서비스 질문창에 한 질문에 한국어로 답한다.
입력: question(질문), gate(게이트 판정), candidates(우리 소스에서 찾은 항목. 내 브리핑에 나왔으면 card에 요약·나한테는·설치 명령),
previous_turns(같은 날 앞선 대화. 최근 3턴은 원문, 그 이전은 summary 한 줄), profile(직군·쓰는 도구).
- candidates와 fetch_article로 읽은 원문에 있는 내용만 쓴다. 없는 도구·기능·설치 명령을 지어내지 않는다
- 원문을 더 봐야 할 때만 fetch_article(url)을 부른다. candidates의 url만, 모두 합쳐 {ANSWER_TOOL_CALLS}회까지
- "그거", "설치 명령"처럼 대상이 빠진 질문은 previous_turns에서 이야기한 항목을 대상으로 본다.
  대상을 정할 수 없으면 found false, answer는 "어느 도구 말씀이세요?"로 시작한다
- 답을 찾지 못하면 found false, answer에 "우리 소스에서 못 찾았어요"라고 쓴다
- gate가 unclear면 범위 밖 질문일 수 있다. AI 소식·AI 도구와 관련 없으면 답하지 말고 found false,
  answer에 이 질문창은 AI 소식과 AI 도구 질문만 받는다고 안내한다
- answer는 공백 포함 {schemas.MAX_ANSWER}자 이내. 설치 명령은 원문이나 card에 있는 그대로 옮긴다
- sources는 답에 쓴 항목의 title과 url. found가 true면 한 개 이상 반드시 쓰고, candidates에 있는 url만 쓴다
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식:
{{"found": true, "answer": "...", "sources": [{{"title": "...", "url": "https://..."}}]}}"""


def _fit_answer(text: str) -> str:
    """600자를 넘으면 600자 안의 마지막 문장 끝에서 자르고, 문장 끝이 없으면 글자 수로 자른다. 긴 줄표는 쉼표로."""
    from pipeline.validate import fit_summary

    text = text.replace(" \u2014 ", ", ").replace("\u2014", ", ").strip()
    text, _ = fit_summary(text, schemas.MAX_ANSWER)
    return text if len(text) <= schemas.MAX_ANSWER else text[:schemas.MAX_ANSWER - 1] + "…"


def _answer_problem(result: dict, by_url: dict[str, dict]) -> tuple[dict | None, str | None]:
    """루프 결과를 규격으로 읽는다. 반환: (답, 문제). 출처는 후보 링크만 남기고 제목은 후보 제목으로 바꾼다."""
    if result["status"] != "ok":
        return None, "도구만 부르고 답을 내지 않았다. 받은 결과로 바로 답한다"
    output = result["output"]
    if not isinstance(output, dict) or set(output) == {"text"}:
        return None, "JSON 객체가 아니다"
    try:
        parsed = schemas.AnswerOutput.model_validate(output)
    except ValueError as exc:
        return None, structured._error_text(exc)
    sources = [{"title": by_url[s.url]["title"], "url": s.url} for s in parsed.sources if s.url in by_url]
    sources = list({s["url"]: s for s in sources}.values())
    if parsed.found and not sources:
        return None, "found가 true인데 sources에 candidates의 url이 없다"
    return {"found": parsed.found, "answer": _fit_answer(parsed.answer), "sources": sources}, None


async def answer(question: str, gate: str, candidates: list[dict], previous_turns: list[dict], profile: dict, *,
                 user_id: int | None = None, mcp_url: str = loop.DEFAULT_MCP_URL, model_call=None) -> dict:
    """질문 답변 (부록 E 2·4). 형식이 틀리면 이유를 알려 1회 다시 부른다. 도구 호출은 두 번 합쳐 3회까지.

    반환: {status: ok|format_failed, found, answer, sources, calls, tool_calls, problem?}. 모델 장애는 ModelUnavailable로 올린다.
    """
    call = model_call or partial(models.call, temperature=0)
    by_url = {c["url"]: c for c in candidates}
    payload = json.dumps({"question": question, "gate": gate, "candidates": candidates, "previous_turns": previous_turns,
                          "profile": profile}, ensure_ascii=False)
    calls = tool_calls = 0
    problem = None
    with tracing.span("answer", kind="chain", input={"gate": gate, "candidates": list(by_url),
                                                     "previous_turns": [t.get("turn_no") for t in previous_turns]}) as span:
        for _ in (1, 2):
            system = ANSWER_PROMPT if problem is None else f"{ANSWER_PROMPT}\n\n직전 출력이 규격에 맞지 않았다 ({problem}). 규격대로 다시 출력한다."
            result = await loop.run(ROLE, system, payload, ["fetch_article"], ANSWER_MAX_STEPS, mcp_url=mcp_url,
                                    briefing_user=user_id, model_call=call, max_tool_calls=ANSWER_TOOL_CALLS - tool_calls)
            calls += result["steps"]
            tool_calls += result["tool_calls"]
            parsed, problem = _answer_problem(result, by_url)
            if parsed:
                outcome = {"status": "ok", **parsed, "calls": calls, "tool_calls": tool_calls}
                break
        else:
            outcome = {"status": "format_failed", "found": False, "answer": "", "sources": [], "calls": calls,
                       "tool_calls": tool_calls, "problem": problem}
        span.update(output=outcome)
    return outcome
