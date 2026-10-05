"""Groq 무료 모델 확인: 목록 API에 있는지, 실제 도구 호출·한글 한 줄·JSON이 되는지, 한도 헤더.

실행: uv run python -m tests.models.check_groq
- 후보는 models.py에 남겨 둔 groq 정의(GROQ_FAST·GROQ_KOREAN, 2026-10-05 개발 모델표에서 뺌) + 도구 호출 지원 문서(https://console.groq.com/docs/tool-use)의 비교 후보
- 키 값은 출력하지 않는다. 한도 헤더는 숫자만 남긴다
결과: tests/models/groq_models.json
"""
import json
import sys
import time
from pathlib import Path

import httpx

import config  # noqa: F401  .env를 os.environ에 채운다
import models
import os
import providers

HERE = Path(__file__).parent
MODELS_URL = "https://api.groq.com/openai/v1/models"
COMPARE = ["llama-3.3-70b-versatile", "qwen/qwen3.6-27b"]
TOOL = {"type": "function", "function": {
    "name": "fetch_article", "description": "기사 원문을 가져온다",
    "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}}
TITLE = "n8n ships a native MCP client node so workflows can call external AI tools"


def post(client: httpx.Client, body: dict) -> tuple[int, dict, dict, float]:
    started = time.perf_counter()
    response = client.post(providers.GROQ_URL, json=body)
    limits = {k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit")}
    return response.status_code, response.json(), limits, round(time.perf_counter() - started, 2)


def check(client: httpx.Client, spec: dict) -> dict:
    model, reasoning = spec["model"], spec.get("reasoning")
    extra = {"reasoning_effort": reasoning} if reasoning else {}
    status, data, limits, seconds = post(client, {"model": model, "temperature": 0, "max_tokens": 300, **extra, "tools": [TOOL],
                                                  "messages": [{"role": "user", "content": "https://github.com/n8n-io/n8n 기사를 도구로 읽어줘"}]})
    calls = (data.get("choices") or [{}])[0].get("message", {}).get("tool_calls") or [] if status == 200 else []
    tool = {"status": status, "supported": bool(calls), "call": calls[0]["function"] if calls else None,
            "error": None if status == 200 else str(data.get("error", {}).get("message"))[:160], "seconds": seconds}
    time.sleep(2.1)  # 분당 30회
    status, data, _, seconds = post(client, {"model": model, "temperature": 0, "max_tokens": 200, **extra,
                                             "messages": [{"role": "user", "content": f"다음 영문 제목을 한 줄 한글로 요약해. 요약 한 줄만 써.\n{TITLE}"}]})
    korean = (data["choices"][0]["message"]["content"] or "").strip() if status == 200 else f"HTTP {status}"
    time.sleep(2.1)
    status, data, _, seconds_json = post(client, {"model": model, "temperature": 0, "max_tokens": 200, **extra,
                                                  "response_format": {"type": "json_object"},
                                                  "messages": [{"role": "user", "content": 'JSON만: {"topic": "mcp_tools", "reason": "한 줄 한국어 이유"}'}]})
    try:
        json_ok = status == 200 and isinstance(json.loads(data["choices"][0]["message"]["content"]), dict)
    except (json.JSONDecodeError, KeyError, TypeError):
        json_ok = False
    time.sleep(2.1)
    return {"model": model, "reasoning": reasoning, "tool_call": tool, "korean": korean, "korean_seconds": seconds,
            "json_object": json_ok, "json_seconds": seconds_json,
            "limits": {k: v for k, v in limits.items() if "limit" in k and "reset" not in k}}


def main() -> int:
    headers = {"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"}
    table_specs = {s["model"]: s for s in (models.GROQ_FAST, models.GROQ_KOREAN)}
    specs = list(table_specs.values()) + [{"model": m} for m in COMPARE if m not in table_specs]
    with httpx.Client(headers=headers, timeout=60) as client:
        listed = client.get(MODELS_URL)
        if listed.status_code != 200:
            print(json.dumps({"models_api": listed.status_code, "pass": False}, ensure_ascii=False))
            return 1
        available = sorted(m["id"] for m in listed.json()["data"] if m.get("active", True))
        rows = [check(client, s) | {"listed": s["model"] in available} for s in specs]
    in_table = [r for r in rows if r["model"] in table_specs]
    checks = {
        "목록_API_200": True,
        "모델표_groq_모델이_목록에_있음": all(r["listed"] for r in in_table),
        "모델표_groq_모델_도구호출_성공": all(r["tool_call"]["supported"] for r in in_table),
        "모델표_groq_모델_JSON_응답": all(r["json_object"] for r in in_table),
    }
    report = {"available_models": available, "rows": rows, "checks": checks, "pass": all(checks.values())}
    (HERE / "groq_models.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
