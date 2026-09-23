"""같은 소식 겹침 빼기 검수 (2026-09-23). 가짜 모델로 확인한다. 네트워크·DB를 쓰지 않는다.

실행: uv run python -m tests.agent.check_same_story
- 묶음마다 앞(중요 순) 하나만 남기고 순서는 그대로, 빈 자리는 채우지 않는다 / 겹침 없으면 그대로
- 한 장 이하면 모델을 부르지 않는다 / 모델에는 제목만 간다
- 범위 밖·두 묶음에 든 id는 규격 실패로 1회 다시 묻고, 그래도 틀리면 그대로 / 모델 장애면 그대로 두고 장애 기록
- 기본 모델은 해설가 순서(MODEL_ROLE)를 빌린다
- pick_for_user가 고른 뉴스에서 겹침을 빼고 same_story_dropped를 남긴다
실제 모델 측정(9/23 제목 7묶음, 겹침 9건): qwen3.8-27b 8건 뺌·잘못 뺀 것 0, gemma3:12b는 서로 다른 소식 5건 중 3건을 잘못 뺐다.
"""
import asyncio
import json
import sys

from langchain_core.messages import AIMessage

import models
from agent import curator, same_story
from agent.structured import Stats

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


def fake(*answers):
    seen = []
    queue = list(answers)

    def call(role, messages, tools=None):
        seen.append(messages[-1].content)
        return AIMessage(content=queue.pop(0) if len(queue) > 1 else queue[0],
                         usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    return call, seen


PICKS = [{"title": t, "url": f"u{n}"} for n, t in enumerate(["GPT-6 공개", "Opus 5.5", "GPT-6 한국어 기사", "Muse", "Opus 한국어"], 1)]


async def main() -> None:
    call, seen = fake('{"groups": [[1, 3], [2, 5]]}')
    kept, n = await same_story.drop(PICKS, Stats(), call)
    check("묶음마다 앞 하나만, 순서 그대로, 채우지 않음", [k["url"] for k in kept] == ["u1", "u2", "u4"] and n == 2)
    check("모델에는 제목만 감", "u1" not in seen[0] and "GPT-6 공개" in seen[0])
    call, _ = fake('{"groups": []}')
    kept, n = await same_story.drop(PICKS, Stats(), call)
    check("겹침 없으면 그대로", kept == PICKS and n == 0)
    call, seen = fake('{"groups": []}')
    kept, n = await same_story.drop(PICKS[:1], Stats(), call)
    check("한 장이면 모델을 안 부름", kept == PICKS[:1] and not seen)
    call, seen = fake('{"groups": [[1, 9]]}', '{"groups": [[1, 1]]}')
    kept, n = await same_story.drop(PICKS, Stats(), call)
    check("범위 밖·중복 id는 다시 묻고 그래도 틀리면 그대로", kept == PICKS and n == 0 and len(seen) == 2)

    def down(role, messages, tools=None):
        raise models.ModelUnavailable("explainer", ["groq 503"])
    stats = Stats()
    kept, n = await same_story.drop(PICKS, stats, down)
    check("모델 장애면 그대로 두고 기록", kept == PICKS and n == 0 and any("같은 소식" in str(f) for f in stats.model_failures))

    roles = []
    original = models.call
    models.call = lambda role, messages, tools=None, **kw: roles.append(role) or AIMessage(
        content='{"groups": []}', usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    try:
        await same_story.drop(PICKS, Stats())
    finally:
        models.call = original
    check("기본 모델은 해설가 순서", roles == [same_story.MODEL_ROLE] == ["explainer"])

    selected = [{"type": "news", "title": p["title"], "url": p["url"], "topic": "model_release", "reason": "r", "source": "s"} for p in PICKS]
    memory = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {"model_release": 3}, "seen_urls": []}
    answers = iter(['{"news": [{"id": 1, "why": "모델 소식"}, {"id": 2, "why": "모델 소식"}, {"id": 3, "why": "모델 소식"}], "tools": []}',
                    '{"groups": [[1, 3]]}'])

    def pick_call(role, messages, tools=None):
        return AIMessage(content=next(answers), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    plan = await curator.pick_for_user(selected, memory, Stats(), pick_call)
    check("pick_for_user가 겹침을 빼고 기록", len(plan["news"]) == 2 and plan["same_story_dropped"] == 1
          and [i["rank"] for i in plan["news"]] == [1, 2])


asyncio.run(main())
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
