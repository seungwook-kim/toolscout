"""뉴스 중요도 점수 (Jev, 2026-09-23 사용자 결정). 오늘의 큰 소식(agent/headline.py)이 이 점수를 쓴다.

선별 모델(로컬 gemma)이 판정하면서 곁들여 매긴 중요도는 평범한 기업 소식에도 4~5점을 줬다(9/23 골든셋 순위상관 0.82).
Jev는 문서 하나와 단계 기준을 받아 단계별 확률과 가중 점수를 돌려주는 판단 전용 모델이다(골든셋 0.94).
- 선별 통과 뉴스마다 제목·요약 300자를 보내 5단계 점수를 받는다. 단계 설명은 영어(공식 가이드상 영어가 가장 정확)
- 받은 점수(1~5 실수)를 반올림해 importance에 넣고 원래 값·confidence는 importance_jev·importance_conf에 남긴다
- 공개 뉴스만 보낸다. 사용자 프로필·질문은 보내지 않는다 (작업 규칙 7, 이 사이트의 학습 사용 정책은 공개돼 있지 않다)
- 키 없음·오류·시간 초과면 그 기사는 선별 모델 점수를 그대로 둔다 (브리핑을 막지 않는다). 동시 호출 4개
호출 주소와 키 이름은 models.JEV (사용자가 산 키가 jevtypesafeai.com 것이라 그 사이트 주소로 부른다).
"""
import asyncio
import logging
import os

import httpx

import models
from agent import tracing

log = logging.getLogger("toolscout.importance")

LEVELS = ["1: Unrelated to AI development, local/municipal news, or a tiny personal side project",
          "2: Niche tool, small startup funding, or a company case study using existing AI models",
          "3: Useful general update: feature, pricing change, notable product or research news",
          "4: Notable model release from a smaller lab, major policy/legal/security event in AI",
          "5: Major lab launches a new flagship model or platform that the whole industry will cover the same day"]
INSTRUCTIONS = "How big is this news for developers who build AI agents, across the whole industry?"
SUMMARY_CHARS, CONCURRENCY, TIMEOUT = 300, 4, 20.0


def _request(item: dict) -> dict:
    return {"state": {"title": item["title"], "summary": (item.get("summary") or "")[:SUMMARY_CHARS]},
            "questions": {"importance": {"type": "score", "instructions": INSTRUCTIONS, "criteria": LEVELS}}}


def _score(answer: dict) -> float:
    """단계 번호가 0부터면 1을 더해 1~5로 맞춘다."""
    probs = answer.get("probabilities") or {}
    return answer["score"] + (1 if probs and min(int(k) for k in probs) == 0 else 0)


async def rescore(selected: list[dict], post=None) -> dict:
    """selected 뉴스의 importance를 Jev 점수로 바꾼다(제자리). 반환: {scored, failed, skipped, cost_usd}."""
    news = [i for i in selected if i.get("type") == "news"]
    key = os.environ.get(models.JEV["key_env"], "")
    if not news or (not key and post is None):
        return {"scored": 0, "failed": 0, "skipped": len(news), "cost_usd": 0.0}
    gate = asyncio.Semaphore(CONCURRENCY)
    report = {"scored": 0, "failed": 0, "skipped": 0, "cost_usd": 0.0}
    errors: list[str] = []
    with tracing.span("importance", kind="chain", model=models.JEV["model"], input={"news": len(news)}) as span, \
            httpx.Client(timeout=TIMEOUT) as client:
        send = post or (lambda body: client.post(models.JEV["url"], headers={"Authorization": f"Bearer {key}"}, json=body))

        async def one(item: dict) -> None:
            async with gate:
                try:
                    response = await asyncio.to_thread(send, _request(item))
                    response.raise_for_status()
                    data = response.json()
                    answer = data["answers"]["importance"]
                    item["importance_jev"], item["importance_conf"] = round(_score(answer), 2), answer.get("confidence")
                    item["importance"] = min(5, max(1, round(item["importance_jev"])))
                    report["scored"] += 1
                    report["cost_usd"] += float((data.get("usage") or {}).get("cost_usd") or 0)
                except Exception as exc:  # 이 기사는 선별 모델 점수를 그대로 쓴다
                    report["failed"] += 1
                    errors.append(f"{type(exc).__name__} {getattr(getattr(exc, 'response', None), 'status_code', '')}".strip())

        await asyncio.gather(*(one(item) for item in news))
        report["cost_usd"] = round(report["cost_usd"], 6)
        span.update(output=report | {"errors": sorted(set(errors))[:5]})
    if report["failed"]:
        log.warning("Jev 중요도 %d건 실패(%s), 선별 모델 점수를 그대로 씀", report["failed"], ", ".join(sorted(set(errors))[:3]))
    return report
