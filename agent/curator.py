"""큐레이터 (계획안 5장, 부록 B 1~3). 선별 → 사용자별 후보 → 검증 요청 목록.

- 선별: 정리된 항목을 무작위로 섞어 20건씩 묶어 판정한다 (AI 관련·오늘 볼 만함·주제·근거 한 줄)
- 사용자별: 기억(프로필·가중치·본 항목)을 읽어 뉴스 최대 5 + 도구 최대 3. 본 항목과 가중치 -5 주제는 뺀다
  성립하지 않으면 줄이고, 0건이면 "오늘 비움"과 이유를 남긴다
- 검증 요청: MCP·스킬 후보 중 하루 최대 5건. 이번 단계에서는 목록만 만들고 검증관은 부르지 않는다
- 관련 카드(F3-b, 월요일): 쌓인 도구 목록에서 미리 좁힌 후보(pipeline/persist.related_pool) 중 최대 3개. 오늘 후보와 겹치면 뺀다
- 되돌림 1(replan_failed): 검증관이 실패로 낸 도구 대신 "대체 항목 선택" 또는 "비움"을 판단한다. 고정 규칙이 아니다 (pipeline/rollback.py가 부른다)
모델 출력은 agent/schemas.py 규격으로 검사하고, 형식이 틀리면 1회 다시 부른다 (agent/structured.py).
모델 장애(제공자 전부 실패)는 선별 묶음·사용자·검증 요청 단위로 건너뛰고 이유를 stats.model_failures에 남긴다.
"""
import random
from dataclasses import asdict
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import models
from agent import card_why, headline, importance, owners, same_story, schemas, structured, tracing
from agent.structured import Stats

ROLE = "curator"
BATCH = 20
SUMMARY_CHARS = 200
# 사용자별 후보 단계 입력 상한. 로컬 모델 문맥 8192토큰에서 후보 140건(약 7.7K토큰)을 넣자 답이 잘려 빈 후보가 됐다 (2026-09-15)
PICK_MAX_NEWS, PICK_MAX_TOOLS, PICK_REASON_CHARS, PICK_SUMMARY_CHARS = 60, 20, 60, 120
# 중요도(agent/importance.py, Jev) 이 값 이하 뉴스는 사용자 후보에서 뺀다. 남는 뉴스가 PICK_MIN_STRONG건 미만이면 빼지 않는다.
# 9/25 본인 뉴스 5장 중 4장이 모델 출시로 잘못 분류된 고객 사례였고, Jev는 이런 사례에 2~2.5점을 줬다 (2026-09-25)
LOW_IMPORTANCE, PICK_MIN_STRONG = 2, 10
# 사용자 뉴스는 원문이 이 시간 안인 것만 (2026-10-16 사용자 "더 빠른 뉴스"). 하루 1회 실행 24시간 + 피드 지연 여유 2시간.
# 수집 창(sources/collect.NEWS_WINDOW 48시간)은 큰 소식의 다룬 곳 세기에 그대로 쓴다
FRESH_NEWS = timedelta(hours=26)
TOOL_TYPES = ("mcp", "skill")
TOPIC_LINES = "\n".join(f"  - {key}: {label}. {schemas.TOPIC_GUIDE[key]}" for key, label in schemas.TOPICS.items())
JSON_ONLY = "출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다."

SELECT_PROMPT = f"""너는 toolscout 큐레이터다. AI 에이전트를 만드는 개발자가 오늘 볼 AI 소식과 도구를 고른다.
입력 항목마다 판정한다.
- ai_related: AI, LLM, 에이전트, MCP, AI 개발 도구와 직접 관련 있으면 true
- worth_today: 개발자가 오늘 알아둘 새 소식·새 도구·의미 있는 업데이트면 true. 광고, 잡담, 단순 질문 글, 오래된 재탕은 false
  행사·컨퍼런스 세션 예고와 연사 소개, 참가·등록 안내, 책·서평·신간 소개, 웨비나·강의·교육 과정 모집, 채용 공고도 false
  (행사 자리에서 새 모델·제품을 실제로 발표한 기사는 true)
  에세이·칼럼·의견 글, 개인 사용기·비교 후기, 커뮤니티 토론 글도 false
  AI 기업의 투자 유치·인수·실적, AI 서비스 장애·보안 사고, 신제품 발표 예고, 연구 결과 공개는 true
  뉴스(type news)는 ai_related만으로 후보가 된다. worth_today는 뉴스에서는 기록용이고 도구 판정에 쓴다
- topic: 아래 주제 id 중 하나. 제목에 나온 단어가 아니라 이 글이 주로 무엇을 발표·다루는지로 정한다
  (예: 은행이 기존 모델로 상담을 자동화한 사례는 model_release가 아니라 industry, 새 AI 칩 발표는 coding_tools가 아니라 industry)
  agent_framework·mcp_tools·coding_tools는 개발 방법·도구 자체를 다룰 때만 쓴다. 제품 출시·기업 소식은 industry, 사고·규제·사회 문제는 safety_policy
{TOPIC_LINES}
- importance: 개발자 전체에게 얼마나 큰 소식인지 1~5. 5는 주요 회사의 새 모델·제품 공개처럼 여러 매체가 함께 다룰 소식, 1은 작은 개인 프로젝트·단신
- reason: 판정 근거를 한국어 한 줄로 (80자 이내)
입력의 모든 id를 빠짐없이 한 번씩 판정한다.
{JSON_ONLY} 형식: {{"judgments": [{{"id": 1, "ai_related": true, "worth_today": true, "topic": "mcp_tools", "importance": 3, "reason": "..."}}]}}"""

PICK_PROMPT = f"""너는 toolscout 큐레이터다. 한 사용자의 기억(프로필·주제 가중치)을 보고 오늘 후보 중 이 사용자에게 보여줄 항목을 고른다.
- news: 뉴스 후보에서 최대 {schemas.MAX_NEWS}건, tools: 도구 후보에서 최대 {schemas.MAX_TOOLS}건. 중요한 순서로 쓴다
- 직군·쓰는 도구·자유 한 줄과 실제로 이어지는 항목만 고른다. 연결이 약하면 개수를 줄이고 억지로 채우지 않는다
- 같은 발표·같은 출시·같은 사건을 다룬 뉴스는 언어·매체가 달라도 하나만 고른다(공식 발표 원문이 있으면 그것). 남는 자리는 다른 소식으로 채운다
- 가중치가 음수인 주제는 뒤로 미루고 양수인 주제는 앞으로 당긴다
- 뉴스의 importance(1~5, 별점)가 높을수록 먼저 고른다. 별점이 낮은 뉴스는 프로필과 분명히 이어질 때만 고른다
- 자유 한 줄에 보기 싫다고 적힌 기술·주제·회사는 고르지 않는다. 이 제외는 다른 기준보다 먼저다
- why: 이 사용자에게 왜 이 카드인지 한국어 한 줄 (80자 이내). 프로필의 무엇(직군·쓰는 도구·자유 한 줄·가중치 높은 주제)과 이어지는지
  구체적으로 쓰고 "~해서 골랐습니다"처럼 합니다체로 끝낸다. "관심 있는 개발자에게 유용한 도구입니다"처럼 어느 항목에나 붙는 말은 쓰지 않는다
- 뉴스와 도구가 모두 0건이면 empty_reason에 이유를 한 줄로 쓴다
{JSON_ONLY} 형식: {{"news": [{{"id": 1, "why": "..."}}], "tools": [{{"id": 1, "why": "..."}}], "empty_reason": null}}"""

RELATED_PICK_INPUT, RELATED_DESCRIPTION_CHARS = 30, 100  # 로컬 모델 문맥 8192토큰 안에 들게 후보 단계와 비슷한 크기로
RELATED_PROMPT = f"""너는 toolscout 큐레이터다. 주 1회 관련 카드로, 날짜와 상관없이 이 사용자에게 맞는 MCP·스킬을 최대 {schemas.MAX_RELATED}개 고른다.
- 후보는 사용자의 쓰는 도구 태그·써봤음 도구·주제 가중치로 미리 좁혀 둔 순서다. match는 후보 이름·설명에 들어간 사용자 도구 이름이다
- 쓰는 도구·직군·자유 한 줄과 실제로 이어지는 것만 고른다. 연결이 약하면 적게 고르고 0개도 된다
- why: 이 사용자에게 왜 이 도구인지 한국어 한 줄 (80자 이내). 무엇과 이어지는지 드러낸다
{JSON_ONLY} 형식: {{"tools": [{{"id": 1, "why": "..."}}]}}"""

REPLAN_PROMPT = f"""너는 toolscout 큐레이터다. 이 사용자에게 고른 도구 하나가 검증관 검증에서 실패했다(설치 실패 또는 원문 접근 불가).
아직 고르지 않은 후보 중 이 사용자에게 맞는 것을 하나 고르거나(replace), 억지로 채우지 않고 비운다(empty).
- 입력: failed(실패한 도구·실패 이유), candidates(대체 후보, id·이름·주제·설명), profile, weights
- 후보가 없거나 쓰는 도구·직군과 이어지는 게 없으면 empty. replace면 id에 후보 번호
- why: 고른 이유나 비운 이유를 한국어 한 줄 (80자 이내)
{JSON_ONLY} 형식: {{"action": "replace", "id": 1, "why": "..."}} 또는 {{"action": "empty", "id": null, "why": "..."}}"""

VERIFY_PROMPT = f"""너는 toolscout 큐레이터다. 오늘 도구 후보 중 검증관에게 실제 확인을 맡길 항목을 하루 최대 {schemas.MAX_VERIFY}건 고른다.
- 개발자에게 쓸모가 커 보이고 설치·동작 확인 가치가 있는 것을 고른다. 확인 가치가 낮으면 적게 고른다
- depth: full(npm·pypi 등 설치해 실행해 볼 MCP), remote(원격 엔드포인트만 있는 MCP), read(SKILL.md를 읽어 볼 스킬)
- reason: 왜 검증할지 한국어 한 줄 (80자 이내)
{JSON_ONLY} 형식: {{"requests": [{{"id": 1, "depth": "full", "reason": "..."}}]}}"""


def _ask(prompt, payload, schema, stats: Stats, check=None, label: str = "", model_call=None):
    return structured.ask_json(ROLE, prompt, payload, schema, stats, check, label, model_call)


def _brief(item: dict, n: int) -> dict:
    site = (urlsplit(item.get("url") or "").hostname or "").removeprefix("www.") if item["type"] == "news" and not item.get("summary") else ""  # 10/5 승인
    return {"id": n, "type": item["type"], "source": item["source"], "title": item["title"], "summary": item.get("summary", "")[:SUMMARY_CHARS]} | ({"link_site": site} if site else {})


def _passes(item: dict, judgment: dict) -> bool:
    """뉴스는 AI 관련이면 후보, 도구는 AI 관련이고 오늘 볼 만해야 후보 (2026-10-16 사용자 결정 \"B로 가자\": 뉴스는 별점(중요도) 순으로 고른다)."""
    return bool(judgment["ai_related"] and (item["type"] == "news" or judgment["worth_today"]))


def _reused(item: dict, known: dict) -> bool:
    return item["type"] == "news" and item.get("url") in known


async def select(items: list[dict], stats: Stats, rng: random.Random, model_call=None, known: dict | None = None,
                 judged: list | None = None) -> list[dict]:
    """20건 묶음 판정. 반환: AI 관련이고 오늘 볼 만한 항목 (topic·reason이 붙는다).
    known: 오늘·어제 판정이 있는 뉴스(agent/select_memo.py)는 모델에 보내지 않고 그 판정을 쓴다. judged: 모델이 판정한 뉴스를 여기에 모은다."""
    known = known or {}
    order = [i for i, item in enumerate(items) if not _reused(item, known)]
    rng.shuffle(order)
    selected = [{**item, **{k: known[item["url"]][k] for k in ("topic", "importance", "reason")}} for item in items
                if _reused(item, known) and _passes(item, known[item["url"]])]
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
            if judged is not None and items[batch[judgment.id - 1]]["type"] == "news":
                judged.append({"url": items[batch[judgment.id - 1]].get("url"), "title": items[batch[judgment.id - 1]]["title"],
                               **judgment.model_dump(include={"ai_related", "worth_today", "topic", "importance", "reason"})})
            if _passes(items[batch[judgment.id - 1]], judgment.model_dump()):
                selected.append({**items[batch[judgment.id - 1]], "topic": judgment.topic, "importance": judgment.importance,
                                 "reason": judgment.reason})
    return selected


def _pick_pool(news: list[dict], tools: list[dict], weights: dict) -> tuple[list[dict], list[dict]]:
    """후보 단계에 넣을 항목. 중요도 낮은 뉴스를 빼고(남는 게 충분할 때만), 상한을 넘으면 뉴스는 주제 가중치 > 별점(중요도) > 공식·매체·커뮤니티 > 최신,
    도구는 가중치 > 별 수 순으로 자른다."""
    from pipeline.dedupe import SOURCE_TIER

    strong = [i for i in news if i.get("importance", 3) > LOW_IMPORTANCE]
    news = strong if len(strong) >= PICK_MIN_STRONG else news
    news = sorted(news, key=lambda i: str(i.get("published_at") or ""), reverse=True)
    news.sort(key=lambda i: (-weights.get(i["topic"], 0), -i.get("importance", 3), SOURCE_TIER.get(i["source"], 9)))
    tools = sorted(tools, key=lambda i: (-weights.get(i["topic"], 0), -(i.get("stars") or 0)))
    return news[:PICK_MAX_NEWS], tools[:PICK_MAX_TOOLS]


def _rank_by_weight(picks: list[dict], weights: dict) -> list[dict]:
    """모델이 고른 순서를 주제 가중치로 한 번 더 정렬한다 (피드백 루프, 부록 C "다음 날 큐레이터가 가중치를 읽어 정렬").
    가중치가 같으면 모델 순서를 그대로 둔다 (안정 정렬)."""
    ordered = sorted(picks, key=lambda item: -weights.get(item["topic"], 0))
    return [item | {"rank": rank} for rank, item in enumerate(ordered, 1)]


async def pick_for_user(selected: list[dict], memory: dict, stats: Stats, model_call=None,
                        fresh_since: datetime | None = None) -> dict:
    """사용자 한 명의 후보. 반환: {user_id, news, tools, empty, empty_reason, failed, failure_reason, excluded}.
    fresh_since가 있으면 원문이 그보다 오래된 뉴스는 뺀다(excluded.stale)."""
    if models.dev_mode() and not memory.get("is_test"):
        raise PermissionError("개발 모드에서는 is_test 사용자만 무료 모델에 보낸다 (작업 규칙 7)")
    seen, weights = set(memory.get("seen_urls", [])), memory.get("weights", {})
    fresh = [item for item in selected if item["url"] not in seen and weights.get(item["topic"], 0) > -5]
    news_all = [item for item in fresh if item["type"] == "news" and headline.is_fresh(item, fresh_since)]
    stale = sum(item["type"] == "news" for item in fresh) - len(news_all)
    tools_all = [item for item in fresh if item["type"] in TOOL_TYPES]
    news, tools = _pick_pool(news_all, tools_all, weights)
    tools, same_owner = owners.spread(tools, memory.get("seen_recent_urls", []))
    plan = {"user_id": memory["user_id"], "news": [], "tools": [], "empty": False, "empty_reason": None,
            "failed": False, "failure_reason": None,
            "excluded": {"seen": sum(item["url"] in seen for item in selected), "weight_minus5": len(selected) - len(fresh)
                         - sum(item["url"] in seen for item in selected),
                         "over_pick_cap": len(news_all) + len(tools_all) - len(news) - len(tools) - same_owner,
                         "same_owner": same_owner, "stale": stale}}
    if not news and not tools:
        return plan | {"empty": True, "empty_reason": "오늘 선별된 새 항목이 없거나 모두 이미 봤다"}
    payload = {"profile": memory["profile"], "weights": {schemas.TOPICS[t]: w for t, w in weights.items() if t in schemas.TOPICS},
               "news": [{"id": n, "title": i["title"], "topic": schemas.TOPICS[i["topic"]], "importance": i.get("importance", 3),
                         "reason": i["reason"][:PICK_REASON_CHARS]} for n, i in enumerate(news, 1)],
               "tools": [{"id": n, "title": i["title"], "topic": schemas.TOPICS[i["topic"]],
                          "summary": i.get("summary", "")[:PICK_SUMMARY_CHARS]} for n, i in enumerate(tools, 1)]}

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
    picked, plan["same_story_dropped"] = await same_story.drop([{**news[p.id - 1], "why": p.why} for p in parsed.news], stats, model_call)
    # 카드의 "이 카드인 이유"는 데이터 근거로, 모델이 쓴 이유는 pick_why로 트레이스에만 (agent/card_why.py)
    plan["news"] = card_why.attach(_rank_by_weight(picked, weights), memory)
    plan["tools"] = card_why.attach(_rank_by_weight([{**tools[p.id - 1], "why": p.why} for p in parsed.tools], weights), memory)
    plan["weights"] = {schemas.TOPICS[t]: w for t, w in weights.items() if t in schemas.TOPICS}  # 트레이스에 가중치가 보이게
    if not plan["news"] and not plan["tools"]:
        plan |= {"empty": True, "empty_reason": parsed.empty_reason or "프로필과 이어지는 항목이 없다"}
    return plan


async def pick_related(pool: list[dict], memory: dict, exclude_urls: set[str], stats: Stats, model_call=None) -> list[dict]:
    """관련 카드 후보 최대 3개. 모델이 고른 것을 이름이 겹치는 수 > 주제 가중치 순으로 한 번 더 정렬한다 (부록 C "노션 계열 도구가 상위").
    반환 항목에는 related=True, why, summary(원문 설명)가 붙는다. 모델 장애·형식 실패면 빈 목록."""
    weights = memory.get("weights", {})
    # 일반 도구 후보와 같은 규칙(9/28 월요일 관련 카드에 빠져 있었다): 최근 7일 본 게시자·같은 게시자 반복 빼기, 이유는 데이터 근거
    candidates = owners.spread([item for item in pool if item["url"] not in exclude_urls],
                               memory.get("seen_recent_urls", []))[0][:RELATED_PICK_INPUT]
    if not candidates:
        return []
    payload = {"profile": memory["profile"], "weights": {schemas.TOPICS[t]: w for t, w in weights.items() if t in schemas.TOPICS},
               "tools": [{"id": n, "title": i["title"], "topic": schemas.TOPICS.get(i["topic"], i["topic"]),
                          "description": (i.get("description") or "")[:RELATED_DESCRIPTION_CHARS], "match": i.get("match", [])}
                         for n, i in enumerate(candidates, 1)]}

    def ids_valid(parsed: schemas.RelatedPicks):
        ids = [p.id for p in parsed.tools]
        if len(set(ids)) != len(ids) or any(not 1 <= i <= len(candidates) for i in ids):
            raise ValueError("tools id가 후보 범위 밖이거나 중복")

    label = f"사용자 {memory['user_id']} 관련 카드"
    try:
        parsed = await _ask(RELATED_PROMPT, payload, schemas.RelatedPicks, stats, ids_valid, label, model_call)
    except models.ModelUnavailable as exc:
        stats.model_failed(label, exc)
        return []
    picks = [{**candidates[p.id - 1], "why": p.why} for p in (parsed.tools if parsed else [])]
    picks.sort(key=lambda i: (-len(i.get("match", [])), -weights.get(i["topic"], 0)))
    picks = card_why.attach(picks, memory)
    return [i | {"related": True, "summary": i.get("description") or "", "rank": n} for n, i in enumerate(picks, 1)]


async def replan_failed(failed: dict, candidates: list[dict], memory: dict, stats: Stats, model_call=None) -> dict:
    """되돌림 1 판단. 반환: {action: replace|empty|failed, item?, why}. 모델 장애·형식 실패면 failed(그 도구만 빠진다)."""
    candidates = candidates[:PICK_MAX_TOOLS]
    weights = memory.get("weights", {})
    payload = {"failed": {"title": failed["title"], "topic": schemas.TOPICS.get(failed.get("topic"), failed.get("topic")),
                          "reason": failed.get("verify_failure") or "검증 실패"},
               "candidates": [{"id": n, "title": c["title"], "topic": schemas.TOPICS.get(c.get("topic"), c.get("topic")),
                               "summary": (c.get("summary") or "")[:PICK_SUMMARY_CHARS]} for n, c in enumerate(candidates, 1)],
               "profile": memory["profile"], "weights": {schemas.TOPICS[t]: w for t, w in weights.items() if t in schemas.TOPICS}}

    def id_valid(parsed: schemas.ReplanDecision):
        if parsed.action == "replace" and not (parsed.id and 1 <= parsed.id <= len(candidates)):
            raise ValueError("replace인데 id가 후보 범위 밖")

    label = f"사용자 {memory['user_id']} 되돌림 1"
    try:
        parsed = await _ask(REPLAN_PROMPT, payload, schemas.ReplanDecision, stats, id_valid, label, model_call)
    except models.ModelUnavailable as exc:
        return {"action": "failed", "why": stats.model_failed(label, exc)}
    if parsed is None:
        return {"action": "failed", "why": "되돌림 판단 형식 실패"}
    if parsed.action == "replace":
        return {"action": "replace", "item": candidates[parsed.id - 1], "why": parsed.why}
    return {"action": "empty", "why": parsed.why}


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


async def run(items: list[dict], memories: list[dict], seed: int | None = None, model_call=None,
              related_pools: dict[int, list[dict]] | None = None, known: dict | None = None,
              fresh_since: datetime | None = None) -> dict:
    """큐레이터 전체. 반환: {selected, plans, verify, stats, seed, format_failed, select_failed, judged}. model_call은 검수용 가짜 모델 주입.

    related_pools(사용자별 관련 카드 후보)가 있으면 그 사용자 plan에 related를 붙인다 (월요일).
    known: 다시 판정하지 않을 뉴스 판정(agent/select_memo.load). judged: 오늘 모델이 판정한 뉴스(select_memo.save에 넘긴다).
    fresh_since: 사용자 뉴스와 큰 소식에 쓸 원문 시각 하한(실행 시각 - FRESH_NEWS). 없으면 거르지 않는다(검수).

    select_failed: 선별 묶음이 모두 모델 장애였다. 이때 사용자별 후보는 만들지 않고 모두 failed로 둔다.
    """
    seed = seed if seed is not None else random.randrange(1 << 30)
    stats = Stats()
    with tracing.span("curator", kind="chain", input={"items": len(items), "users": len(memories), "seed": seed}) as span:
        judged: list[dict] = []
        selected = await select(items, stats, random.Random(seed), model_call, known or {}, judged)
        batches = -(-sum(not _reused(i, known or {}) for i in items) // BATCH)
        select_failed = batches > 0 and sum(f["label"].startswith("선별") for f in stats.model_failures) == batches
        tops, scored = [], None
        if select_failed:
            plans = [{"user_id": m["user_id"], "news": [], "tools": [], "empty": False, "empty_reason": None, "failed": True,
                      "failure_reason": "선별 묶음 전부 모델 장애", "excluded": {}} for m in memories]
            verify = []
        else:
            plans = []
            scored = await importance.rescore(selected) if model_call is None else None  # 검수(가짜 모델)에서는 Jev를 부르지 않는다
            tops = await headline.pick(selected, stats, model_call, fresh_since)
            for memory in memories:
                plan = headline.attach(await pick_for_user(selected, memory, stats, model_call, fresh_since), tops, memory)
                if related_pools is not None and not plan["failed"] and memory["user_id"] in related_pools:
                    today_urls = {i["url"] for i in plan["news"] + plan["tools"]}
                    plan["related"] = await pick_related(related_pools[memory["user_id"]], memory, today_urls, stats, model_call)
                    if plan["related"]:
                        plan["empty"], plan["empty_reason"] = False, None
                plans.append(plan)
            verify = await verification_requests(selected, stats, model_call)
        result = {"selected": selected, "plans": plans, "verify": verify, "stats": asdict(stats), "seed": seed,
                  "headlines": [{k: t[k] for k in ("title", "url", "coverage", "score", "group_titles")} for t in tops], "importance": scored,
                  "format_failed": stats.unrecovered > 0, "select_failed": select_failed, "trace_id": span.trace_id, "judged": judged}
        span.update(output={"selected": len(selected), "reused": sum(_reused(i, known or {}) for i in items),
                            "plans": [(p["user_id"], len(p["news"]), len(p["tools"]), len(p.get("related", []))) for p in plans],
                            "weights": {p["user_id"]: p.get("weights", {}) for p in plans},
                            "headlines": result["headlines"], "importance": scored,  # 큰 소식이 빠진 날 원인을 트레이스에서 본다
                            "verify": len(verify), "stats": asdict(stats) | {"failure_examples": len(stats.failure_examples)}})
    return result
