"""오늘의 큰 소식 (2026-09-23 사용자 결정). 사용자 관심도와 상관없이 뉴스 맨 위에 고정하는 칸. 1칸, 두 번째도 8점 이상이면 2칸.

9/23 아침 오퍼스 5.5 공개가 본인 브리핑에서 빠졌다. 뉴스는 관심도로만 줄 세워, 관심도가 어긋나면 업계 전체가 다룬 소식도 밀린다.
하루 1회 모든 사용자 공통으로 고른다.
- 후보: 선별 통과 뉴스 중 중요도(선별 모델이 매긴 1~5, Jev가 다시 매김) 3 이상, 중요도 > 출처 등급 순으로 최대 80건.
  2026-10-08 30건에서 늘림: 30건에서 자른 뒤 묶어서 커뮤니티 기사(GeekNews 하이쿠 5.5)가 잘려 다룬 곳 수가 적게 세어졌다.
  묶기는 제목만 보내므로 80건도 한 번에 묶는다
- 같은 소식 묶기(agent/same_story.groups)로 묶어 묶음마다 점수 = 최고 중요도 + (다룬 곳 수 - 1) + 공식 발표 있으면 1
- 다룬 곳 3곳 이상이거나, 중요도 5를 2곳 이상이 다뤘을 때만. 없으면 그날은 칸을 비운다
- 두 번째로 높은 소식도 8점 이상이면 같이 올린다 (9/23 GPT-6 9점·오퍼스 5.5 8점, 사용자 결정)
- 대표 기사는 공식 발표 > 매체 > 커뮤니티 순. 같은 소식의 다른 기사는 사용자 뉴스에서 뺀다
- 이미 본 소식(묶음의 어느 링크든 본 적 있음)이면 그 사용자에게는 넣지 않는다. 주제 가중치가 -5여도 넣는다
  (계획안 부록 C "그 주제는 카드에 안 나오되 헤드라인엔 남음", 9/23 "관심도와 상관없이". 9/28 예외 처리 점검에서 어긋난 것을 바로잡음)
모델 장애·형식 실패면 칸을 비운다 (브리핑을 막지 않는다). Jev 같은 점수 전용 모델은 보류했다 (2026-09-23 사용자 결정).
"""
from agent import same_story, schemas
from agent.structured import Stats

CANDIDATES, MIN_IMPORTANCE = 80, 3
MIN_COVERAGE, MIN_COVERAGE_TOP = 3, 2
MAX_HEADLINES, SECOND_MIN_SCORE = 2, 8


def _tier(item: dict) -> int:
    from pipeline.dedupe import SOURCE_TIER
    return SOURCE_TIER.get(item.get("source"), 9)


async def pick(selected: list[dict], stats: Stats, model_call=None) -> list[dict]:
    """오늘의 큰 소식 0~2건(점수 순). 각각 대표 기사 + {headline, coverage, score, group_urls, why}."""
    pool = sorted((i for i in selected if i["type"] == "news" and i.get("importance", 3) >= MIN_IMPORTANCE),
                  key=lambda i: (-i.get("importance", 3), _tier(i)))[:CANDIDATES]
    if len(pool) < MIN_COVERAGE_TOP:
        return []
    found = await same_story.groups(pool, stats, model_call, "큰 소식 묶기")
    if found is None:
        return []
    ranked = []
    for group in found:
        members = [pool[n - 1] for n in group]
        top = max(i.get("importance", 3) for i in members)
        official = any(_tier(i) == 1 for i in members)
        if not (len(members) >= MIN_COVERAGE or (top == 5 and len(members) >= MIN_COVERAGE_TOP)):
            continue
        ranked.append((top + len(members) - 1 + official, members))
    ranked.sort(key=lambda r: -r[0])
    chosen = ranked[:1] + [r for r in ranked[1:MAX_HEADLINES] if r[0] >= SECOND_MIN_SCORE]
    return [{**min(members, key=lambda i: (_tier(i), -i.get("importance", 3))), "headline": True, "coverage": len(members),
             "score": score, "group_urls": [i["url"] for i in members],
             "why": f"오늘 {len(members)}곳이 함께 다룬 큰 소식이라 관심 주제와 상관없이 맨 위에 둡니다"} for score, members in chosen]


def attach(plan: dict, tops: list[dict], memory: dict) -> dict:
    """사용자 plan 뉴스 맨 위에 큰 소식을 넣고 같은 소식의 다른 기사는 뺀다. 뉴스는 모두 합쳐 MAX_NEWS장."""
    if plan.get("failed"):
        return plan
    seen = set(memory.get("seen_urls", []))
    tops = [t for t in tops if not seen & set(t["group_urls"])]
    if not tops:
        return plan
    covered = {u for t in tops for u in t["group_urls"]}
    rest = [i for i in plan["news"] if i["url"] not in covered][:schemas.MAX_NEWS - len(tops)]
    plan["news"] = [item | {"rank": rank} for rank, item in enumerate(tops + rest, 1)]
    plan["headline"] = [t["title"] for t in tops]
    if plan.get("empty"):
        plan["empty"], plan["empty_reason"] = False, None
    return plan
