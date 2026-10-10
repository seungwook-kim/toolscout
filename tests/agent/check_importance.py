"""중요도 검수 (Jev 2026-09-23, 개발 모드 구독 대체 2026-10-05·10-06). 가짜 응답으로 확인한다. Jev·모델·네트워크를 부르지 않는다.

실행: uv run python -m tests.agent.check_importance
운영 모드(Jev만, DEV_MODE=0으로 확인)
- 뉴스만 보내고 도구는 안 보냄 / 요청에는 제목·요약 300자와 5단계 영어 기준만 (사용자 정보 없음)
- 점수 반올림해 importance, 원래 값·confidence는 따로 / 단계 번호가 0부터면 1을 더함 / 1~5 밖으로 안 나감
- 실패한 기사는 선별 모델 점수 그대로, 나머지는 반영 / 키 없으면 아무것도 안 보냄 / 비용 합산
- 모델표: same_story는 [Haiku 5.5, OpenRouter gpt-4o-mini], 역할표 4개는 그대로 / Jev 주소는 models.JEV
- same_story 첫 칸(Haiku 5.5) 시간 초과면 둘째 칸(gpt-4o-mini)으로
개발 모드(2026-10-06 "JEV로 돌려": Jev가 먼저, 못 매긴 기사만 구독 대체)
- Jev가 다 매기면 구독 모델을 부르지 않음 / Jev가 실패한 기사만 "importance" 역할 모델로, 키가 없으면 전부
- 대체는 20건 묶음마다 한 번 / 입력은 번호·제목·요약 300자(요약이 비면 link_site)만, 기준은 같은 5단계
- 받은 점수로 importance를 바꾸고 선별 점수는 importance_select에 / 도구는 손대지 않음
- 번호가 빠진 답은 1회 다시 묻고 그래도 틀리면, 모델 장애면 그 묶음은 선별 점수 그대로
공통
- curator.run은 가짜 모델(검수)일 때 중요도 모델·Jev를 부르지 않는다
- 중요도 2 이하 뉴스는 사용자 후보에서 빠짐(남는 게 10건 미만이면 그대로)
"""
import asyncio
import json
import os
import sys
from contextlib import contextmanager

import models
from agent import curator, importance

results: list[tuple[str, bool]] = []


@contextmanager
def mode(value: str):
    saved = os.environ.get("DEV_MODE")
    os.environ["DEV_MODE"] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = saved


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


def scorer(answers=None, broken=()):
    """가짜 중요도 모델. 받은 번호마다 answers(제목→점수, 없으면 2)를 돌려준다. 첫 제목이 broken에 든 묶음은 번호 하나를 빼고 답한다."""
    from langchain_core.messages import AIMessage
    seen: list[dict] = []

    def call(role, messages, tools=None):
        payload = json.loads(messages[-1].content.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
        seen.append({"role": role, "system": messages[0].content, "input": payload, "retry": "규격에 맞지 않았다" in messages[0].content})
        scores = [{"id": p["id"], "importance": (answers or {}).get(p["title"], 2)} for p in payload]
        if payload[0]["title"] in broken:
            scores = scores[1:]
        return AIMessage(json.dumps({"scores": scores}), usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    return call, seen


def blocked(body):
    import httpx
    raise httpx.ConnectError("연결 끊김")  # 10/1~10/5 안랩 차단 때와 같은 실패


@contextmanager
def no_key():
    saved = os.environ.pop(models.JEV["key_env"], None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ[models.JEV["key_env"]] = saved


async def dev_checks() -> None:
    from langchain_core.messages import AIMessage

    def never(role, messages, tools=None):
        raise AssertionError("Jev가 다 매겼는데 구독 모델을 불렀다")
    data = items()
    with mode("1"):
        report = await importance.rescore(data, post=lambda b: answer(3.0), model_call=never)
    check("개발: Jev가 다 매기면 구독 모델 안 부름", report["scored"] == 3 and "fallback" not in report
          and all(i["importance"] == 4 for i in data if i["type"] == "news"))

    data = items()
    call, seen = scorer({"구글북": 1, "실패할 기사": 2})
    with mode("1"):
        report = await importance.rescore(data, post=lambda b: answer(3.0) if b["state"]["title"] == "Opus 5.5" else blocked(b),
                                          model_call=call)
    by = {i["url"]: i for i in data}
    check("개발: Jev가 실패한 기사만 구독으로 다시 매김", [p["title"] for p in seen[0]["input"]] == ["구글북", "실패할 기사"]
          and by["u1"]["importance"] == 4 and "importance_select" not in by["u1"]
          and by["u2"]["importance"] == 1 and by["u2"]["importance_select"] == 5 and by["u3"]["importance"] == 2
          and report["scored"] == 1 and report["failed"] == 2 and report["fallback"]["scored"] == 2)

    data = items() + [{"type": "news", "title": "요약 빈 글", "summary": "", "url": "https://www.example.com/a", "importance": 3}]
    call, seen = scorer({"Opus 5.5": 5, "구글북": 1})
    with mode("1"):
        report = await importance.rescore(data, post=blocked, model_call=call)
    by = {i["url"]: i for i in data}
    sent = seen[0]["input"]
    check("개발: Jev가 전부 막히면 전부 구독으로, 선별 점수는 importance_select에", by["u1"]["importance"] == 5
          and by["u1"]["importance_select"] == 3 and by["u2"]["importance"] == 1 and "importance_jev" not in by["u1"])
    check("개발: 도구는 손대지 않고 뉴스만 보냄", by["u4"]["importance"] == 3 and "importance_select" not in by["u4"]
          and [p["title"] for p in sent] == ["Opus 5.5", "구글북", "실패할 기사", "요약 빈 글"])
    check("개발: 입력은 번호·제목·요약 300자, 요약이 비면 link_site", all(set(p) <= {"id", "title", "summary", "link_site"} for p in sent)
          and len(sent[0]["summary"]) == 300 and sent[3].get("link_site") == "example.com" and "link_site" not in sent[0])
    check("개발: 같은 5단계 기준이 프롬프트에", all(level in seen[0]["system"] for level in importance.LEVELS))
    check("개발: 보고 Jev 실패 4·대체 성공 4", report["failed"] == 4 and report["fallback"] == {"scored": 4, "failed": 0, "skipped": 0, "cost_usd": 0.0})

    many = [{"type": "news", "title": f"n{n}", "url": f"m{n}", "importance": 4} for n in range(25)]
    call, seen = scorer(broken={"n20"})
    with mode("1"), no_key():
        report = await importance.rescore(many, model_call=call)
    first, second = [s for s in seen if not s["retry"]], [s for s in seen if s["retry"]]
    check("개발: 키가 없으면 전부 구독, 20건 묶음마다 한 번 (25건 → 2묶음)", report["skipped"] == 25 and [len(s["input"]) for s in first] == [20, 5])
    check("개발: 번호 빠진 묶음은 1회 다시 묻고, 그래도 틀리면 선별 점수 그대로", len(second) == 1
          and all(i["importance"] == 2 for i in many[:20]) and all(i["importance"] == 4 for i in many[20:])
          and report["fallback"]["scored"] == 20 and report["fallback"]["failed"] == 5)

    def down(role, messages, tools=None):
        raise models.ModelUnavailable("importance", ["claude_code 529", "claude_code 529"])
    kept = [{"type": "news", "title": "a", "url": "a", "importance": 4}]
    with mode("1"):
        report = await importance.rescore(kept, post=blocked, model_call=down)
    check("개발: Jev도 구독도 실패하면 선별 점수 그대로", kept[0]["importance"] == 4 and report["fallback"]["failed"] == 1)

    roles, original = [], models.call
    models.call = lambda role, messages, tools=None, **kw: roles.append(role) or AIMessage(
        '{"scores": [{"id": 1, "importance": 3}]}', usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    try:
        with mode("1"), no_key():
            await importance.rescore([{"type": "news", "title": "a", "url": "a"}])
    finally:
        models.call = original
    check("개발: 대체의 기본 모델은 importance 역할", roles == ["importance"])


async def main() -> None:
    sent = []
    replies = {"Opus 5.5": answer(3.9), "구글북": answer(1.6), "실패할 기사": Resp({}, 500)}

    def post(body):
        sent.append(body)
        return replies[body["state"]["title"]]
    data = items()
    with mode("0"):  # 운영 모드: Jev만. 개발 모드는 실패한 기사를 구독 모델로 다시 매긴다(dev_checks)
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
    with mode("0"):
        await importance.rescore(one, post=lambda b: answer(4.2, zero_based=False))
    check("1부터 단계면 그대로 (4.2→4)", one[0]["importance"] == 4)
    edge = [{"type": "news", "title": "a", "url": "a"}]
    with mode("0"):
        await importance.rescore(edge, post=lambda b: answer(5.0))
    check("1~5 밖으로 안 나감 (5.0+1→5)", edge[0]["importance"] == 5)
    with mode("0"), no_key():
        none = await importance.rescore(items())
    check("운영: 키 없으면 아무것도 안 보냄", none == {"scored": 0, "failed": 0, "skipped": 3, "cost_usd": 0.0})
    with mode("0"):
        prod_same_story = models.active_models()["same_story"]
    check("운영 모델표: same_story는 [Haiku 5.5, gpt-4o-mini(OpenRouter)], 역할표 4개 그대로",
          prod_same_story == [{"provider": "anthropic", "model": "claude-haiku-5-5"}, {"provider": "openrouter", "model": "openai/gpt-4o-mini"}]
          and set(models.DEV_MODELS) == set(models.PROD_MODELS) == {"curator", "verifier", "explainer", "gate"})
    await dev_checks()
    check("Jev 주소는 models.JEV", models.JEV["url"].endswith("/api/v1/decide") and models.JEV["key_env"] == "JEV_API_KEY")

    import httpx
    from langchain_core.messages import AIMessage as AI, HumanMessage
    seen_models = []

    def flaky(model, messages, tools, **kw):
        seen_models.append(model)
        raise httpx.ReadTimeout("timed out")

    def fallback_ok(model, messages, tools, **kw):
        seen_models.append(model)
        return AI('{"groups": []}', usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    saved_adapter, saved_interval = dict(models.PROVIDERS), dict(models.FREE_TIER_MIN_INTERVAL)
    models.PROVIDERS["anthropic"], models.PROVIDERS["openrouter"] = flaky, fallback_ok
    models.FREE_TIER_MIN_INTERVAL.clear()
    try:
        with mode("0"):
            reply = models.call("same_story", [HumanMessage("x")])
    finally:
        models.PROVIDERS.update(saved_adapter)
        models.FREE_TIER_MIN_INTERVAL.update(saved_interval)
    check("운영: same_story 첫 칸(Haiku 5.5) 시간 초과면 둘째 칸(gpt-4o-mini)이 답함",
          seen_models == ["claude-haiku-5-5", "openai/gpt-4o-mini"] and reply.text == '{"groups": []}'
          and reply.response_metadata["slot"] == "fallback")

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
