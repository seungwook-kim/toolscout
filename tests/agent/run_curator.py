"""큐레이터 검수 (계획안 5장 큐레이터, 부록 B 1~3). 오늘 실제 수집 데이터 + 개발 프로필(is_test). A·B 두 브리핑을 비교한다.

실행: uv run python -m tests.agent.run_curator
결과: tests/agent/curator_report.json (제목·근거·숫자만)
큐레이터 전체 결과(요약 포함)는 저장소가 아니라 임시 폴더에 둔다. 해설가 검수가 읽는다.
"""
import asyncio
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import memory
from agent import curator, schemas, tracing
from pipeline.dedupe import dedupe
from pipeline.normalize import normalize

HERE = Path(__file__).parent
ITEMS_CACHE = Path(tempfile.gettempdir()) / "toolscout_items_today.json"
RESULT_CACHE = Path(tempfile.gettempdir()) / "toolscout_curator_result.json"


def load_items() -> list[dict]:
    if ITEMS_CACHE.exists():
        return json.loads(ITEMS_CACHE.read_text(encoding="utf-8"))
    from sources.collect import collect

    return [item for result in collect() for item in result.items]


def picked_urls(plan: dict) -> set[str]:
    return {item["url"] for item in plan["news"] + plan["tools"]}


def main() -> int:
    items = dedupe(normalize(load_items()))
    memories = [memory.read(uid) for uid in memory.test_user_ids()]
    started = time.perf_counter()
    with tracing.span("test:curator", kind="chain", input={"items": len(items), "users": [m["user_id"] for m in memories]}) as root:
        result = asyncio.run(curator.run(items, memories))
    seconds = round(time.perf_counter() - started, 1)
    tracing.flush()
    RESULT_CACHE.write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")

    stats, plans, selected = result["stats"], result["plans"], result["selected"]
    a, b = (picked_urls(plans[0]), picked_urls(plans[1])) if len(plans) >= 2 else (set(), set())
    overlap = len(a & b)
    report = {
        "input_items": len(items), "selected": len(selected), "selected_by_type": dict(Counter(i["type"] for i in selected)),
        "topics": dict(Counter(schemas.TOPICS[i["topic"]] for i in selected)), "seed": result["seed"],
        "calls": stats["calls"], "tokens": {"input": stats["input_tokens"], "output": stats["output_tokens"]}, "seconds": seconds,
        "format_failures": stats["format_failures"], "unrecovered": stats["unrecovered"],
        "failure_examples": stats["failure_examples"],
        "users": [{"user_id": p["user_id"], "role": m["profile"]["role"], "empty": p["empty"], "empty_reason": p["empty_reason"],
                   "news": [{"title": i["title"], "why": i["why"]} for i in p["news"]],
                   "tools": [{"title": i["title"], "why": i["why"]} for i in p["tools"]]} for p, m in zip(plans, memories)],
        "overlap_items": overlap,
        "reason_examples": [{"title": i["title"], "topic": schemas.TOPICS[i["topic"]], "reason": i["reason"]} for i in selected[:3]],
        "verify": [{"title": v["title"], "depth": v["depth"], "reason": v["verify_reason"]} for v in result["verify"]],
        "trace_url": tracing.trace_url(root.trace_id),
    }
    checks = {
        "형식_재시도_후_실패_없음": stats["unrecovered"] == 0,
        "is_test_사용자_2명_이상": len(memories) >= 2 and all(m["is_test"] for m in memories),
        "사용자별_뉴스5·도구3_이하": all(len(p["news"]) <= schemas.MAX_NEWS and len(p["tools"]) <= schemas.MAX_TOOLS for p in plans),
        "도구는_본_항목_제외": all(i["url"] not in set(m["seen_urls"]) for p, m in zip(plans, memories) for i in p["tools"]),
        "비움이면_이유_있음": all(p["empty_reason"] for p in plans if p["empty"]),
        "검증_요청_5건_이하": len(result["verify"]) <= schemas.MAX_VERIFY,
        "두_사용자_항목_절반_이상_다름": bool(a or b) and overlap <= min(len(a), len(b)) / 2,
        "trace_있음": bool(result["trace_id"]),
    }
    report |= {"checks": checks, "pass": all(checks.values())}
    (HERE / "curator_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
