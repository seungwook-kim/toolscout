"""큐레이터 (계획안 5장, 부록 B 1~3). 선별 → 사용자별 후보 → 검증 요청 목록.

- 선별: 정리된 항목을 무작위로 섞어 20건씩 묶어 판정한다 (AI 관련·오늘 볼 만함·주제·근거 한 줄)
- 사용자별: 기억(프로필·가중치·본 항목)을 읽어 뉴스 최대 5 + 도구 최대 3. 본 항목과 가중치 -5 주제는 뺀다
  성립하지 않으면 줄이고, 0건이면 "오늘 비움"과 이유를 남긴다
- 검증 요청: MCP·스킬 후보 중 하루 최대 5건. 이번 단계에서는 목록만 만들고 검증관은 부르지 않는다
모델 출력은 agent/schemas.py 규격으로 검사하고, 형식이 틀리면 1회 다시 부른다 (agent/structured.py).
모델 장애(제공자 전부 실패)는 선별 묶음·사용자·검증 요청 단위로 건너뛰고 이유를 stats.model_failures에 남긴다.
"""
import random
from dataclasses import asdict

import models
from agent import schemas, structured, tracing
from agent.structured import Stats

ROLE = "curator"
BATCH = 20
SUMMARY_CHARS = 200
TOOL_TYPES = ("mcp", "skill")
TOPIC_LINES = "\n".join(f"  - {key}: {label}" for key, label in schemas.TOPICS.items())
JSON_ONLY = "출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다."

SELECT_PROMPT = f"""너는 toolscout 큐레이터다. AI 에이전트를 만드는 개발자가 오늘 볼 AI 소식과 도구를 고른다.
입력 항목마다 판정한다.
- ai_related: AI, LLM, 에이전트, MCP, AI 개발 도구와 직접 관련 있으면 true
- worth_today: 개발자가 오늘 알아둘 새 소식·새 도구·의미 있는 업데이트면 true. 광고, 잡담, 단순 질문 글, 오래된 재탕은 false
- topic: 아래 주제 id 중 하나
{TOPIC_LINES}
- reason: 판정 근거를 한국어 한 줄로 (80자 이내)
입력의 모든 id를 빠짐없이 한 번씩 판정한다.
{JSON_ONLY} 형식: {{"judgments": [{{"id": 1, "ai_related": true, "worth_today": true, "topic": "mcp_tools", "reason": "..."}}]}}"""

PICK_PROMPT = f"""너는 toolscout 큐레이터다. 한 사용자의 기억(프로필·주제 가중치)을 보고 오늘 후보 중 이 사용자에게 보여줄 항목을 고른다.
- news: 뉴스 후보에서 최대 {schemas.MAX_NEWS}건, tools: 도구 후보에서 최대 {schemas.MAX_TOOLS}건. 중요한 순서로 쓴다
- 직군·쓰는 도구·자유 한 줄과 실제로 이어지는 항목만 고른다. 연결이 약하면 개수를 줄이고 억지로 채우지 않는다
- 가중치가 음수인 주제는 뒤로 미루고 양수인 주제는 앞으로 당긴다
- why: 이 사용자에게 왜 이 카드인지 한국어 한 줄 (80자 이내). 프로필의 무엇과 이어지는지 드러낸다
- 뉴스와 도구가 모두 0건이면 empty_reason에 이유를 한 줄로 쓴다
{JSON_ONLY} 형식: {{"news": [{{"id": 1, "why": "..."}}], "tools": [{{"id": 1, "why": "..."}}], "empty_reason": null}}"""

VERIFY_PROMPT = f"""너는 toolscout 큐레이터다. 오늘 도구 후보 중 검증관에게 실제 확인을 맡길 항목을 하루 최대 {schemas.MAX_VERIFY}건 고른다.
- 개발자에게 쓸모가 커 보이고 설치·동작 확인 가치가 있는 것을 고른다. 확인 가치가 낮으면 적게 고른다
- depth: full(npm·pypi 등 설치해 실행해 볼 MCP), remote(원격 엔드포인트만 있는 MCP), read(SKILL.md를 읽어 볼 스킬)
- reason: 왜 검증할지 한국어 한 줄 (80자 이내)
{JSON_ONLY} 형식: {{"requests": [{{"id": 1, "depth": "full", "reason": "..."}}]}}"""


def _ask(prompt, payload, schema, stats: Stats, check=None, label: str = "", model_call=None):
    return structured.ask_json(ROLE, prompt, payload, schema, stats, check, label, model_call)


def _brief(item: dict, n: int) -> dict:
    return {"id": n, "type": item["type"], "source": item["source"], "title": item["title"],
            "summary": item.get("summary", "")[:SUMMARY_CHARS]}


async def select(items: list[dict], stats: Stats, rng: random.Random, model_call=None) -> list[dict]:
    """20건 묶음 판정. 반환: AI 관련이고 오늘 볼 만한 항목 (topic·reason이 붙는다)."""
    order = list(range(len(items)))
    rng.shuffle(order)
    selected = []
    for start in range(0, len(order), BATCH):
        batch = order[start:start + BATCH]

        def ids_complete(parsed: schemas.SelectionBatch, size=len(batch)):
            ids = sorted(j.id for j in parsed.judgments)
            if ids != list(range(1, size + 1)):
                raise ValueError(f"id가 1~{size}를 한 번씩 덮지 않음 (받은 {len(ids)}건)")

        label = f"선별 {start // BATCH + 1}묶음"
        try:
            parsed = await _ask(SELECT_PROMPT, [_brief(items[i], n) for n, i in enumerate(batch, 1)],
                                schemas.SelectionBatch, stats, ids_complete, label, model_call)
        except models.ModelUnavailable as exc:
            stats.model_failed(label, exc)
            continue
        for judgment in parsed.judgments if parsed else []:
            if judgment.ai_related and judgment.worth_today:
                selected.append({**items[batch[judgment.id - 1]], "topic": judgment.topic, "reason": judgment.reason})
    return selected


async def pick_for_user(selected: list[dict], memory: dict, stats: Stats, model_call=None) -> dict:
    """사용자 한 명의 후보. 반환: {user_id, news, tools, empty, empty_reason, failed, failure_reason, excluded}."""
    if models.dev_mode() and not memory.get("is_test"):
        raise PermissionError("개발 모드에서는 is_test 사용자만 무료 모델에 보낸다 (작업 규칙 7)")
    seen, weights = set(memory.get("seen_urls", [])), memory.get("weights", {})
    fresh = [item for item in selected if item["url"] not in seen and weights.get(item["topic"], 0) > -5]
    news = [item for item in fresh if item["type"] == "news"]
    tools = [item for item in fresh if item["type"] in TOOL_TYPES]
    plan = {"user_id": memory["user_id"], "news": [], "tools": [], "empty": False, "empty_reason": None,
            "failed": False, "failure_reason": None,
            "excluded": {"seen": sum(item["url"] in seen for item in selected), "weight_minus5": len(selected) - len(fresh)
                         - sum(item["url"] in seen for item in selected)}}
    if not news and not tools:
        return plan | {"empty": True, "empty_reason": "오늘 선별된 새 항목이 없거나 모두 이미 봤다"}
    payload = {"profile": memory["profile"], "weights": {schemas.TOPICS[t]: w for t, w in weights.items() if t in schemas.TOPICS},
               "news": [{"id": n, "title": i["title"], "source": i["source"], "topic": schemas.TOPICS[i["topic"]],
                         "reason": i["reason"]} for n, i in enumerate(news, 1)],
               "tools": [{"id": n, "title": i["title"], "topic": schemas.TOPICS[i["topic"]], "summary": i.get("summary", "")[:SUMMARY_CHARS]}
                         for n, i in enumerate(tools, 1)]}

    def ids_valid(parsed: schemas.UserPicks):
        for name, pool in (("news", news), ("tools", tools)):
            ids = [p.id for p in getattr(parsed, name)]
            if len(set(ids)) != len(ids) or any(not 1 <= i <= len(pool) for i in ids):
                raise ValueError(f"{name} id가 후보 범위 밖이거나 중복")

    label = f"사용자 {memory['user_id']} 후보"
    try:
        parsed = await _ask(PICK_PROMPT, payload, schemas.UserPicks, stats, ids_valid, label, model_call)
    except models.ModelUnavailable as exc:
        return plan | {"failed": True, "failure_reason": stats.model_failed(label, exc)}
    if parsed is None:
        return plan | {"empty": True, "empty_reason": "후보 선정 응답 형식 실패"}
    plan["news"] = [{**news[p.id - 1], "rank": r, "why": p.why} for r, p in enumerate(parsed.news, 1)]
    plan["tools"] = [{**tools[p.id - 1], "rank": r, "why": p.why} for r, p in enumerate(parsed.tools, 1)]
    if not plan["news"] and not plan["tools"]:
        plan |= {"empty": True, "empty_reason": parsed.empty_reason or "프로필과 이어지는 항목이 없다"}
    return plan


async def verification_requests(selected: list[dict], stats: Stats, model_call=None) -> list[dict]:
    tools = [item for item in selected if item["type"] in TOOL_TYPES]
    if not tools:
        return []
    payload = [{**_brief(item, n), "url": item["url"]} for n, item in enumerate(tools, 1)]

    def ids_valid(parsed: schemas.VerifyRequests):
        ids = [r.id for r in parsed.requests]
        if len(set(ids)) != len(ids) or any(not 1 <= i <= len(tools) for i in ids):
            raise ValueError("id가 후보 범위 밖이거나 중복")

    try:
        parsed = await _ask(VERIFY_PROMPT, payload, schemas.VerifyRequests, stats, ids_valid, "검증 요청", model_call)
    except models.ModelUnavailable as exc:
        stats.model_failed("검증 요청", exc)
        return []
    return [{**tools[r.id - 1], "depth": r.depth, "verify_reason": r.reason} for r in (parsed.requests if parsed else [])]


async def run(items: list[dict], memories: list[dict], seed: int | None = None, model_call=None) -> dict:
    """큐레이터 전체. 반환: {selected, plans, verify, stats, seed, format_failed, select_failed}. model_call은 검수용 가짜 모델 주입.

    select_failed: 선별 묶음이 모두 모델 장애였다. 이때 사용자별 후보는 만들지 않고 모두 failed로 둔다.
    """
    seed = seed if seed is not None else random.randrange(1 << 30)
    stats = Stats()
    with tracing.span("curator", kind="chain", input={"items": len(items), "users": len(memories), "seed": seed}) as span:
        selected = await select(items, stats, random.Random(seed), model_call)
        batches = -(-len(items) // BATCH)
        select_failed = batches > 0 and sum(f["label"].startswith("선별") for f in stats.model_failures) == batches
        if select_failed:
            plans = [{"user_id": m["user_id"], "news": [], "tools": [], "empty": False, "empty_reason": None, "failed": True,
                      "failure_reason": "선별 묶음 전부 모델 장애", "excluded": {}} for m in memories]
            verify = []
        else:
            plans = [await pick_for_user(selected, memory, stats, model_call) for memory in memories]
            verify = await verification_requests(selected, stats, model_call)
        result = {"selected": selected, "plans": plans, "verify": verify, "stats": asdict(stats), "seed": seed,
                  "format_failed": stats.unrecovered > 0, "select_failed": select_failed, "trace_id": span.trace_id}
        span.update(output={"selected": len(selected), "plans": [(p["user_id"], len(p["news"]), len(p["tools"])) for p in plans],
                            "verify": len(verify), "stats": asdict(stats) | {"failure_examples": len(stats.failure_examples)}})
    return result
