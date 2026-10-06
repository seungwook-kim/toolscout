"""뉴스 중요도 점수 (Jev, 2026-09-23 사용자 결정). 오늘의 큰 소식(agent/headline.py)이 이 점수를 쓴다.

선별 모델(로컬 gemma)이 판정하면서 곁들여 매긴 중요도는 평범한 기업 소식에도 4~5점을 줬다(9/23 골든셋 순위상관 0.82).
Jev는 문서 하나와 단계 기준을 받아 단계별 확률과 가중 점수를 돌려주는 판단 전용 모델이다(골든셋 0.94).
- 선별 통과 뉴스마다 제목·요약 300자를 보내 5단계 점수를 받는다. 단계 설명은 영어(공식 가이드상 영어가 가장 정확)
- 받은 점수(1~5 실수)를 반올림해 importance에 넣고 원래 값·confidence는 importance_jev·importance_conf에 남긴다
- 공개 뉴스만 보낸다. 사용자 프로필·질문은 보내지 않는다 (작업 규칙 7, 이 사이트의 학습 사용 정책은 공개돼 있지 않다)
- 키 없음·오류·시간 초과면 그 기사는 선별 모델 점수를 그대로 둔다 (브리핑을 막지 않는다). 동시 호출 4개
호출 주소와 키 이름은 models.JEV (사용자가 산 키가 jevtypesafeai.com 것이라 그 사이트 주소로 부른다).

개발 모드도 Jev가 먼저다 (2026-10-06 사용자 결정 "JEV로 돌려". 10/5 밤 하루는 구독만 썼다).
Jev가 못 매긴 기사(키 없음·연결 실패 등)만 Claude 구독(models "importance" 역할)으로 다시 매긴다: 같은 5단계 기준으로
20건 묶음마다 한 번, 선별이 매긴 원래 점수는 importance_select에. 그 묶음도 모델 장애·형식 실패면 선별 점수를 그대로 둔다.
운영 모드는 Jev만(실패하면 선별 점수).
"""
import asyncio
import logging
import os
from urllib.parse import urlsplit

import httpx

import models
from agent import schemas, structured, tracing
from agent.structured import Stats

log = logging.getLogger("toolscout.importance")

LEVELS = ["1: Unrelated to AI development, local/municipal news, or a tiny personal side project",
          "2: Niche tool, small startup funding, or a company case study using existing AI models",
          "3: Useful general update: feature, pricing change, notable product or research news",
          "4: Notable model release from a smaller lab, major policy/legal/security event in AI",
          "5: Major lab launches a new flagship model or platform that the whole industry will cover the same day"]
INSTRUCTIONS = "How big is this news for developers who build AI agents, across the whole industry?"
SUMMARY_CHARS, CONCURRENCY, TIMEOUT = 300, 4, 20.0
MODEL_ROLE, BATCH = "importance", 20
PROMPT = f"""너는 toolscout 편집자다. 뉴스마다 AI 에이전트를 만드는 개발자 업계 전체에게 얼마나 큰 소식인지 1~5점을 매긴다.
질문: {INSTRUCTIONS}
단계:
{chr(10).join(f"- {level}" for level in LEVELS)}
- 제목과 요약(요약이 비면 link_site 도메인)만 보고 매긴다
- 입력의 모든 id에 한 번씩 점수를 준다
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식: {{"scores": [{{"id": 1, "importance": 3}}]}}"""


def _request(item: dict) -> dict:
    return {"state": {"title": item["title"], "summary": (item.get("summary") or "")[:SUMMARY_CHARS]},
            "questions": {"importance": {"type": "score", "instructions": INSTRUCTIONS, "criteria": LEVELS}}}


def _score(answer: dict) -> float:
    """단계 번호가 0부터면 1을 더해 1~5로 맞춘다."""
    probs = answer.get("probabilities") or {}
    return answer["score"] + (1 if probs and min(int(k) for k in probs) == 0 else 0)


def _brief(item: dict, n: int) -> dict:
    site = "" if item.get("summary") else (urlsplit(item.get("url") or "").hostname or "").removeprefix("www.")
    return {"id": n, "title": item["title"], "summary": (item.get("summary") or "")[:SUMMARY_CHARS]} | ({"link_site": site} if site else {})


async def _rescore_by_model(news: list[dict], model_call=None) -> dict:
    """개발 모드 대체: Jev가 못 매긴 뉴스를 구독 모델로 20건 묶음마다 매겨 importance를 바꾼다(제자리). 반환 모양은 Jev와 같다."""
    report = {"scored": 0, "failed": 0, "skipped": 0, "cost_usd": 0.0}
    stats = Stats()
    call = model_call or (lambda _role, messages, tools=None: models.call(MODEL_ROLE, messages, tools, temperature=0))
    with tracing.span("importance_fallback", kind="chain", model=models.active_models()[MODEL_ROLE][0]["model"],
                      input={"news": len(news)}) as span:
        for start in range(0, len(news), BATCH):
            batch = news[start:start + BATCH]

            def ids_complete(parsed: schemas.ImportanceBatch, size=len(batch)):
                ids = sorted(s.id for s in parsed.scores)
                if ids != list(range(1, size + 1)):
                    raise ValueError(f"id가 1~{size}를 한 번씩 덮지 않음 (받은 {len(ids)}건)")

            label = f"중요도 {start // BATCH + 1}묶음"
            try:
                parsed = await structured.ask_json("curator", PROMPT, [_brief(item, n) for n, item in enumerate(batch, 1)],
                                                   schemas.ImportanceBatch, stats, ids_complete, label, call)
            except models.ModelUnavailable as exc:
                stats.model_failed(label, exc)
                parsed = None
            if parsed is None:  # 이 묶음은 선별 모델 점수를 그대로 쓴다
                report["failed"] += len(batch)
                continue
            for score in parsed.scores:
                item = batch[score.id - 1]
                item["importance_select"], item["importance"] = item.get("importance"), score.importance
            report["scored"] += len(batch)
        span.update(output=report | {"model_failures": stats.model_failures[:3], "format_failures": stats.format_failures})
    if report["failed"]:
        log.warning("구독 중요도 %d건 실패, 선별 모델 점수를 그대로 씀", report["failed"])
    return report


async def rescore(selected: list[dict], post=None, model_call=None) -> dict:
    """selected 뉴스의 importance를 Jev 점수로 바꾼다(제자리). 반환: {scored, failed, skipped, cost_usd} (+ 개발 모드 대체는 fallback).
    개발 모드는 Jev가 못 매긴 기사(키 없음·연결 실패 등)만 구독 모델로 다시 매긴다."""
    news = [i for i in selected if i.get("type") == "news"]
    report = await _rescore_jev(news, post)
    left = [i for i in news if "importance_jev" not in i]
    if models.dev_mode() and left:
        report["fallback"] = await _rescore_by_model(left, model_call)
    return report


async def _rescore_jev(news: list[dict], post=None) -> dict:
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
                except Exception as exc:  # 이 기사는 개발 모드면 구독 모델로, 운영 모드면 선별 모델 점수 그대로
                    report["failed"] += 1
                    errors.append(f"{type(exc).__name__} {getattr(getattr(exc, 'response', None), 'status_code', '')}".strip())

        await asyncio.gather(*(one(item) for item in news))
        report["cost_usd"] = round(report["cost_usd"], 6)
        span.update(output=report | {"errors": sorted(set(errors))[:5]})
    if report["failed"]:
        # 10/1~10/5 매일 ConnectError는 이 PC의 안랩 차단이었다(바깥에서는 정상). 연결 실패가 이어지면 안랩부터 본다
        log.warning("Jev 중요도 %d건 실패(%s), %s", report["failed"], ", ".join(sorted(set(errors))[:3]),
                    "구독 모델로 다시 매김" if models.dev_mode() else "선별 모델 점수를 그대로 씀")
    return report
