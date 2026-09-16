"""OpenCode Zen Muse Spark 실제 호출 시험 (2026-09-16 사용자 요청). 대체 전환 없이 opencode 한 제공자만 부른다.

실행: uv run python -m tests.models.try_opencode
- 선별: 공개 뉴스 제목 20건 한 묶음을 큐레이터 선별 프롬프트·규격(SelectionBatch, id 1~20 한 번씩)으로. 첫 응답 형식 통과 여부와 재시도 뒤 결과
- 한국어 요약 3건: 공개 뉴스 제목·요약 → {"summary_ko"} 두 문장 120자 이내, 한글 비율(어절 기준 검증 노드와 같은 함수)
- 도구 호출 1회: fetch_article 도구를 주고 호출하게 한 뒤, 도구 결과를 돌려 최종 답까지 (Responses API 변환 왕복)
- 결과: tests/models/opencode_report.json (응답 시간·형식 통과). 사용자 텍스트는 보내지 않는다 (학습 사용 등급)
"""
import asyncio
import json
import random
import sys
import time
from pathlib import Path

import config  # noqa: F401

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from sqlalchemy import select

import db
import models
from agent import curator, loop, schemas, tracing
from agent.structured import Stats
from pipeline.validate import hangul_ratio

HERE = Path(__file__).parent
SPEC = models.OPENCODE_FREE
TOOL = {"name": "fetch_article", "description": "링크의 기사 원문을 읽어 온다",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}
SUMMARY_PROMPT = """공개 뉴스 한 건을 한국어로 요약한다. 두 문장, 120자 이내, 고유명사는 원문 표기.
출력은 JSON 객체 하나만 쓴다. 형식: {"summary_ko": "..."}"""
timings: list[dict] = []


def only_opencode(role, messages, tools=None, *, temperature=None):
    """대체 전환 없이 opencode만. 호출마다 시간을 잰다."""
    started = time.perf_counter()
    try:
        return models._call_one(role, "primary", SPEC, messages, [convert_to_openai_tool(t) for t in tools] if tools else None, temperature)
    except Exception as exc:  # 대체 전환 없이 보는 시험이라 모든 오류를 모델 장애로 기록한다 (값·키는 담지 않는다)
        raise models.ModelUnavailable(role, [f"opencode {type(exc).__name__}: {config.redact(str(exc))[:200]}"]) from exc
    finally:
        timings.append({"role": role, "seconds": round(time.perf_counter() - started, 1)})


def public_news(limit: int) -> list[dict]:
    with db.get_engine().connect() as conn:
        rows = conn.execute(select(db.Item.title, db.Item.url, db.Item.source, db.Item.description, db.Item.summary_ko)
                            .where(db.Item.type == "news").order_by(db.Item.id.desc()).limit(limit)).all()
    return [{"type": "news", "title": r.title, "url": r.url, "source": r.source, "summary": r.description or r.summary_ko or ""} for r in rows]


async def selection(news: list[dict]) -> dict:
    stats, before = Stats(), len(timings)
    started = time.perf_counter()
    picked = await curator.select(news[:20], stats, random.Random(0), model_call=only_opencode)
    return {"items": len(news[:20]), "selected": len(picked), "seconds": round(time.perf_counter() - started, 1),
            "calls": len(timings) - before, "first_try_ok": stats.format_failures == 0 and not stats.model_failures, "passed": stats.unrecovered == 0 and not stats.model_failures,
            "format_failures": stats.format_failures, "errors": [e["error"][:160] for e in stats.failure_examples],
            "model_failures": [str(m)[:160] for m in stats.model_failures], "topics": sorted({p["topic"] for p in picked})}


async def summaries(news: list[dict]) -> list[dict]:
    out = []
    for item in news[:3]:
        payload = json.dumps({"title": item["title"], "summary": item["summary"][:500]}, ensure_ascii=False)
        started = time.perf_counter()
        try:
            result = await loop.run("curator", SUMMARY_PROMPT, payload, [], 1, model_call=only_opencode)
            text = (result["output"] or {}).get("summary_ko") if isinstance(result["output"], dict) else None
            error = None
        except models.ModelUnavailable as exc:
            text, error = None, str(exc)[:160]
        out.append({"title": item["title"][:60], "seconds": round(time.perf_counter() - started, 1), "json_ok": bool(text),
                    "chars": len(text or ""), "within_120": bool(text) and len(text) <= schemas.MAX_SUMMARY,
                    "hangul_ratio": round(hangul_ratio(text), 2) if text else 0, "summary_ko": text, "error": error})
    return out


def tool_round_trip(url: str) -> dict:
    messages = [SystemMessage("링크 원문을 fetch_article 도구로 읽은 뒤 한국어 한 문장으로 답한다."), HumanMessage(f"이 기사를 읽어 줘: {url}")]
    started = time.perf_counter()
    try:
        first = only_opencode("verifier", messages, [TOOL])
        call = first.tool_calls[0] if first.tool_calls else None
        outcome = {"first_seconds": round(time.perf_counter() - started, 1), "tool_called": bool(call),
                   "tool_name": call and call["name"], "args_ok": bool(call) and call["args"].get("url") == url}
        if call:
            messages += [first, ToolMessage("<data>OpenAI가 새 에이전트 SDK를 공개했다. 도구 호출과 추적 기능이 들어 있다.</data>",
                                            tool_call_id=call["id"], name=call["name"])]
            again = time.perf_counter()
            final = only_opencode("verifier", messages, [TOOL])
            outcome |= {"final_seconds": round(time.perf_counter() - again, 1), "final_text": final.text[:120],
                        "final_ok": bool(final.text.strip()) and not final.tool_calls}
        return outcome
    except models.ModelUnavailable as exc:
        return {"tool_called": False, "error": str(exc)[:160]}
    except Exception as exc:
        return {"tool_called": False, "error": f"{type(exc).__name__}: {config.redact(str(exc))[:160]}"}


def main() -> int:
    news = public_news(20)
    try:
        chosen = asyncio.run(selection(news))
        korean = asyncio.run(summaries(news))
        tool = tool_round_trip(news[0]["url"])
    finally:
        tracing.flush()
    checks = {
        "선별_20건_규격_통과": chosen["passed"],
        "선별_첫응답_형식_통과": chosen["first_try_ok"],
        "한국어_요약_3건_JSON": all(s["json_ok"] for s in korean),
        "한국어_요약_120자·한글비율_0.6": all(s["within_120"] and s["hangul_ratio"] >= 0.6 for s in korean),
        "도구호출_요청": bool(tool.get("tool_called") and tool.get("args_ok")),
        "도구결과_뒤_최종답": bool(tool.get("final_ok")),
    }
    seconds = [t["seconds"] for t in timings]
    report = {"model": f"{SPEC['provider']}:{SPEC['model']}", "calls": len(timings),
              "seconds": {"avg": round(sum(seconds) / len(seconds), 1) if seconds else 0, "max": max(seconds, default=0)},
              "selection": chosen, "summaries": korean, "tool": tool, "checks": checks, "pass": all(checks.values())}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (HERE / "opencode_report.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
