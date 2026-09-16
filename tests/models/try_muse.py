"""Meta Muse Spark 1.3 실제 호출 시험 (OpenRouter 경유, 2026-09-16 사용자 요청). 대체 전환 없이 meta 한 제공자만 부른다.

실행: uv run python -m tests.models.try_muse
- contributor(학습 사용 등급, 공개 뉴스만): (a) 제목 20건 선별 JSON (b) 영문 제목 3건 한글 요약 (c) 도구 호출 1회
- 표준(meta/muse-spark-1.3): (d) 가짜 프로필 A로 카드 1장 (원문은 읽지 않고 요약만)
- 각 단계의 응답 시간·토큰·비용(OpenRouter 모델 목록의 단가로 계산)·형식 통과 여부, 실제로 답한 모델 이름(1.3인지 1.1로 내려갔는지)
- 결과: tests/models/muse_report.json. 사용자가 쓴 텍스트는 보내지 않는다 (작업 규칙 7, is_test 프로필과 공개 뉴스만)
- 2026-09-16 첫 실행은 전부 403 "requires 18+ age confirmation"(OpenRouter 계정 설정). 그 확인 뒤 다시 돌린다
"""
import asyncio
import json
import random
import sys
import time
from pathlib import Path

import config  # noqa: F401

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from sqlalchemy import select

import db
import memory
import models
from agent import curator, explainer, loop, schemas, tracing
from agent.structured import Stats
from pipeline.validate import hangul_ratio

HERE = Path(__file__).parent
MODELS_URL = "https://openrouter.ai/api/v1/models"
TOOL = {"name": "fetch_article", "description": "링크의 기사 원문을 읽어 온다",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
SUMMARY_PROMPT = """공개 뉴스 한 건을 한국어로 요약한다. 두 문장, 120자 이내, 고유명사는 원문 표기.
출력은 JSON 객체 하나만 쓴다. 형식: {"summary_ko": "..."}"""
calls: list[dict] = []


def prices() -> dict[str, dict]:
    """OpenRouter 모델 목록의 토큰 단가 (달러/토큰)."""
    data = httpx.get(MODELS_URL, timeout=30).json().get("data", [])
    return {m["id"]: {k: float(v or 0) for k, v in (m.get("pricing") or {}).items() if k in ("prompt", "completion")}
            for m in data if m["id"].startswith("meta/muse-spark")}


def only_meta(spec: dict, label: str):
    """대체 전환 없이 meta만 부르고 호출마다 시간·토큰·실제 모델을 적는다."""

    def call(role, messages, tools=None, *, temperature=None):
        started = time.perf_counter()
        try:
            result = models._call_one(role, "primary", spec, messages,
                                      [convert_to_openai_tool(t) for t in tools] if tools else None, temperature)
        except Exception as exc:  # 시험이라 모든 오류를 모델 장애로 (값·키는 담지 않는다)
            calls.append({"step": label, "role": role, "seconds": round(time.perf_counter() - started, 1), "error": True})
            raise models.ModelUnavailable(role, [f"meta {type(exc).__name__}: {config.redact(str(exc))[:200]}"]) from exc
        usage = result.usage_metadata or {}
        calls.append({"step": label, "role": role, "model": spec["model"],
                      "served_model": result.response_metadata.get("served_model"),
                      "seconds": round(time.perf_counter() - started, 1),
                      "input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)})
        return result

    return call


def cost(unit: dict[str, dict]) -> dict:
    """호출 기록의 토큰에 단가를 곱해 달러로. 단가를 모르는 모델은 0으로 둔다."""
    total = 0.0
    for c in calls:
        price = unit.get(c.get("model") or "", {})
        total += c.get("input_tokens", 0) * price.get("prompt", 0) + c.get("output_tokens", 0) * price.get("completion", 0)
    return {"usd_total": round(total, 6), "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
            "output_tokens": sum(c.get("output_tokens", 0) for c in calls)}


def public_news(limit: int) -> list[dict]:
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Item.title, db.Item.url, db.Item.source, db.Item.description, db.Item.summary_ko)
                            .where(db.Item.type == "news").order_by(db.Item.id.desc()).limit(limit)).all()
    return [{"type": "news", "title": r.title, "url": r.url, "source": r.source,
             "summary": r.description or r.summary_ko or ""} for r in rows]


async def selection(news: list[dict], call) -> dict:
    stats, before = Stats(), len(calls)
    started = time.perf_counter()
    picked = await curator.select(news[:20], stats, random.Random(0), model_call=call)
    return {"items": len(news[:20]), "selected": len(picked), "seconds": round(time.perf_counter() - started, 1),
            "calls": len(calls) - before, "first_try_ok": stats.format_failures == 0 and not stats.model_failures,
            "passed": stats.unrecovered == 0 and not stats.model_failures, "format_failures": stats.format_failures,
            "errors": [e["error"][:160] for e in stats.failure_examples],
            "model_failures": [str(m)[:160] for m in stats.model_failures], "topics": sorted({p["topic"] for p in picked})}


async def summaries(news: list[dict], call) -> list[dict]:
    out = []
    for item in news[:3]:
        payload = json.dumps({"title": item["title"], "summary": item["summary"][:500]}, ensure_ascii=False)
        started = time.perf_counter()
        try:
            result = await loop.run("curator", SUMMARY_PROMPT, payload, [], 1, model_call=call)
            text = (result["output"] or {}).get("summary_ko") if isinstance(result["output"], dict) else None
            error = None
        except models.ModelUnavailable as exc:
            text, error = None, str(exc)[:160]
        out.append({"title": item["title"][:60], "seconds": round(time.perf_counter() - started, 1), "json_ok": bool(text),
                    "chars": len(text or ""), "within_120": bool(text) and len(text) <= schemas.MAX_SUMMARY,
                    "hangul_ratio": round(hangul_ratio(text), 2) if text else 0, "summary_ko": text, "error": error})
    return out


def tool_round_trip(url: str, call) -> dict:
    messages = [SystemMessage("링크 원문을 fetch_article 도구로 읽은 뒤 한국어 한 문장으로 답한다."), HumanMessage(f"이 기사를 읽어 줘: {url}")]
    started = time.perf_counter()
    try:
        first = call("verifier", messages, [TOOL])
        tool_call = first.tool_calls[0] if first.tool_calls else None
        outcome = {"first_seconds": round(time.perf_counter() - started, 1), "tool_called": bool(tool_call),
                   "tool_name": tool_call and tool_call["name"], "args_ok": bool(tool_call) and tool_call["args"].get("url") == url}
        if tool_call:
            messages += [first, ToolMessage("<data>OpenAI가 새 에이전트 SDK를 공개했다. 도구 호출과 추적 기능이 들어 있다.</data>",
                                            tool_call_id=tool_call["id"], name=tool_call["name"])]
            again = time.perf_counter()
            final = call("verifier", messages, [TOOL])
            outcome |= {"final_seconds": round(time.perf_counter() - again, 1), "final_text": final.text[:120],
                        "final_ok": bool(final.text.strip()) and not final.tool_calls}
        return outcome
    except models.ModelUnavailable as exc:
        return {"tool_called": False, "error": str(exc)[:160]}
    except Exception as exc:
        return {"tool_called": False, "error": f"{type(exc).__name__}: {config.redact(str(exc))[:160]}"}


async def one_card(news: list[dict], call) -> dict:
    """가짜 프로필 A로 카드 1장. MCP 없이(client None) 요약만 보고 쓴다."""
    user_id = memory.test_user_ids()[0]
    mind = {"user_id": user_id, "profile": memory.profile(user_id)}
    item = dict(news[0], why="프로필 관심사와 겹치는 소식", skip_fetch=True)
    stats, started = Stats(), time.perf_counter()
    outcome = await explainer.explain_item(item, mind, None, stats, model_call=call)
    card = outcome.get("card") or {}
    return {"status": outcome["status"], "seconds": round(time.perf_counter() - started, 1),
            "format_failures": stats.format_failures, "reason": str(outcome.get("reason") or "")[:160],
            "summary_ko": card.get("summary_ko"), "for_me": card.get("for_me"),
            "summary_within_120": len(card.get("summary_ko") or "") <= schemas.MAX_SUMMARY if card else False,
            "hangul_ratio": round(hangul_ratio(card.get("summary_ko") or ""), 2) if card else 0}


def main() -> int:
    unit = prices()
    news = public_news(20)
    contributor, standard = only_meta(models.MUSE_CONTRIB, "contributor"), only_meta(models.MUSE_STANDARD, "standard")
    try:
        chosen = asyncio.run(selection(news, contributor))
        korean = asyncio.run(summaries(news, contributor))
        tool = tool_round_trip(news[0]["url"], contributor)
        card = asyncio.run(one_card(news, standard))
    finally:
        tracing.flush()
    served = sorted({c.get("served_model") for c in calls if c.get("served_model")})
    checks = {
        "선별_20건_규격_통과": chosen["passed"],
        "선별_첫응답_형식_통과": chosen["first_try_ok"],
        "한국어_요약_3건_JSON": all(s["json_ok"] for s in korean),
        "한국어_요약_120자·한글비율_0.6": all(s["within_120"] and s["hangul_ratio"] >= 0.6 for s in korean),
        "도구호출_요청": bool(tool.get("tool_called") and tool.get("args_ok")),
        "도구결과_뒤_최종답": bool(tool.get("final_ok")),
        "카드_1장_작성": card["status"] == "card" and card["summary_within_120"] and card["hangul_ratio"] >= 0.6,
        "실제_응답_모델이_1.3": bool(served) and all("1.3" in m for m in served),
    }
    seconds = [c["seconds"] for c in calls]
    report = {"models": {"contributor": models.MUSE_CONTRIB["model"], "standard": models.MUSE_STANDARD["model"]},
              "unit_price_usd_per_token": unit, "served_models": served, "calls": len(calls),
              "seconds": {"avg": round(sum(seconds) / len(seconds), 1) if seconds else 0, "max": max(seconds, default=0)},
              "cost": cost(unit), "selection": chosen, "summaries": korean, "tool": tool, "card": card,
              "checks": checks, "pass": all(checks.values())}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (HERE / "muse_report.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
