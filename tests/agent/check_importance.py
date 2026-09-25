"""Jev 중요도 검수 (2026-09-23). 가짜 응답으로 확인한다. Jev·네트워크를 부르지 않는다.

실행: uv run python -m tests.agent.check_importance
- 뉴스만 보내고 도구는 안 보냄 / 요청에는 제목·요약 300자와 5단계 영어 기준만 (사용자 정보 없음)
- 점수 반올림해 importance, 원래 값·confidence는 따로 / 단계 번호가 0부터면 1을 더함 / 1~5 밖으로 안 나감
- 실패한 기사는 선별 모델 점수 그대로, 나머지는 반영 / 키 없으면 아무것도 안 보냄 / 비용 합산
- 모델표: same_story는 OpenRouter gpt-4o-mini 단일 모델, 역할표 4개는 그대로 / Jev 주소는 models.JEV
- curator.run은 가짜 모델(검수)일 때 Jev를 부르지 않는다
- same_story 시간 초과면 같은 모델로 한 번 더 / 중요도 2 이하 뉴스는 사용자 후보에서 빠짐(남는 게 10건 미만이면 그대로)
"""
import asyncio
import json
import os
import sys

import models
from agent import curator, importance

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


class Resp:
    def __init__(self, body: dict, status: int = 200):
        self.body, self.status_code = body, status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("err", request=None, response=self)

    def json(self):
        return self.body


def answer(score, zero_based=True, conf=0.9):
    probs = {str(i if zero_based else i + 1): 0.2 for i in range(5)}
    return Resp({"answers": {"importance": {"type": "score", "score": score, "confidence": conf, "probabilities": probs}},
                 "usage": {"cost_usd": 0.0002}})


def items():
    return [{"type": "news", "title": "Opus 5.5", "summary": "x" * 500, "url": "u1", "importance": 3},
            {"type": "news", "title": "구글북", "summary": "s", "url": "u2", "importance": 5},
            {"type": "news", "title": "실패할 기사", "summary": "s", "url": "u3", "importance": 4},
            {"type": "mcp", "title": "도구", "summary": "s", "url": "u4", "importance": 3}]


async def main() -> None:
    sent = []
    replies = {"Opus 5.5": answer(3.9), "구글북": answer(1.6), "실패할 기사": Resp({}, 500)}

    def post(body):
        sent.append(body)
        return replies[body["state"]["title"]]
    data = items()
    report = await importance.rescore(data, post=post)
    by = {i["url"]: i for i in data}
    check("뉴스만 보냄", sorted(b["state"]["title"] for b in sent) == sorted(["Opus 5.5", "구글북", "실패할 기사"]))
    body = sent[0]
    check("요청은 제목·요약 300자·영어 5단계 기준만", set(body) == {"state", "questions"} and set(body["state"]) == {"title", "summary"}
          and all(len(b["state"]["summary"]) <= 300 for b in sent) and len(body["questions"]["importance"]["criteria"]) == 5
          and body["questions"]["importance"]["type"] == "score")
    check("0부터 단계면 1 더해 반올림 (3.9→4.9→5, 1.6→2.6→3)", by["u1"]["importance"] == 5 and by["u1"]["importance_jev"] == 4.9
          and by["u2"]["importance"] == 3 and by["u1"]["importance_conf"] == 0.9)
    check("실패한 기사는 선별 점수 그대로, 도구는 손대지 않음", by["u3"]["importance"] == 4 and "importance_jev" not in by["u3"]
          and "importance_jev" not in by["u4"])
    check("보고: 성공 2·실패 1·비용 합산", report["scored"] == 2 and report["failed"] == 1 and abs(report["cost_usd"] - 0.0004) < 1e-9)
    one = [{"type": "news", "title": "a", "url": "a", "importance": 3}]
    await importance.rescore(one, post=lambda b: answer(4.2, zero_based=False))
    check("1부터 단계면 그대로 (4.2→4)", one[0]["importance"] == 4)
    edge = [{"type": "news", "title": "a", "url": "a"}]
    await importance.rescore(edge, post=lambda b: answer(5.0))
    check("1~5 밖으로 안 나감 (5.0+1→5)", edge[0]["importance"] == 5)
    saved = os.environ.pop(models.JEV["key_env"], None)
    try:
        none = await importance.rescore(items())
    finally:
        if saved is not None:
            os.environ[models.JEV["key_env"]] = saved
    check("키 없으면 아무것도 안 보냄", none == {"scored": 0, "failed": 0, "skipped": 3, "cost_usd": 0.0})
    check("모델표: same_story는 gpt-4o-mini 하나를 두 번(같은 모델 재시도), 역할표 4개 그대로",
          models.active_models()["same_story"] == [{"provider": "openrouter", "model": "openai/gpt-4o-mini"}] * 2
          and set(models.DEV_MODELS) == set(models.PROD_MODELS) == {"curator", "verifier", "explainer", "gate"})
    check("Jev 주소는 models.JEV", models.JEV["url"].endswith("/api/v1/decide") and models.JEV["key_env"] == "JEV_API_KEY")

    import httpx
    from langchain_core.messages import AIMessage as AI, HumanMessage
    seen_models = []

    def flaky(model, messages, tools, **kw):
        seen_models.append(model)
        if len(seen_models) == 1:
            raise httpx.ReadTimeout("timed out")
        return AI('{"groups": []}', usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    saved_adapter, saved_interval = models.PROVIDERS["openrouter"], dict(models.FREE_TIER_MIN_INTERVAL)
    models.PROVIDERS["openrouter"] = flaky
    models.FREE_TIER_MIN_INTERVAL.clear()
    try:
        reply = models.call("same_story", [HumanMessage("x")])
    finally:
        models.PROVIDERS["openrouter"] = saved_adapter
        models.FREE_TIER_MIN_INTERVAL.update(saved_interval)
    check("same_story 시간 초과면 같은 모델로 한 번 더", len(seen_models) == 2 and len(set(seen_models)) == 1 and reply.text == '{"groups": []}')

    def news_item(n, imp):
        return {"type": "news", "title": f"n{n}", "url": f"u{n}", "source": "openai", "topic": "model_release", "importance": imp}
    pool, _ = curator._pick_pool([news_item(n, 2) for n in range(4)] + [news_item(n, 4) for n in range(10, 20)], [], {"model_release": 5})
    check("중요도 2 이하 뉴스는 후보에서 빠짐", len(pool) == 10 and all(i["importance"] > 2 for i in pool))
    few, _ = curator._pick_pool([news_item(n, 2) for n in range(4)] + [news_item(n, 4) for n in range(10, 15)], [], {})
    check("남는 뉴스가 10건 미만이면 빼지 않음", len(few) == 9)

    called = []
    original = importance.rescore

    async def spy(selected, post=None):
        called.append(1)
        return {}
    importance.rescore = spy
    try:
        from langchain_core.messages import AIMessage

        def fake(role, messages, tools=None):
            system = messages[0].content
            body = ({"judgments": [{"id": 1, "ai_related": True, "worth_today": True, "topic": "industry", "reason": "판정"}]}
                    if '"judgments"' in system else {"groups": []} if '"groups"' in system else
                    {"news": [], "tools": [], "empty_reason": "없음"} if '"empty_reason"' in system else {"requests": []})
            return AIMessage(json.dumps(body, ensure_ascii=False), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
        await curator.run([{"type": "news", "title": "t", "url": "https://x.test/1", "source": "aitimes", "summary": "s"}],
                          [{"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {}, "seen_urls": []}], seed=1, model_call=fake)
    finally:
        importance.rescore = original
    check("가짜 모델 검수에서는 Jev를 안 부름", called == [])


asyncio.run(main())
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
