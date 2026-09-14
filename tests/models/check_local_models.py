"""로컬 모델(Ollama) 실측: VRAM, 도구 호출, 한글 요약, 선별 20건 응답 시간.

실행: uv run python -m tests.models.check_local_models [모델 ...]
- 모델마다 다른 모델을 내린 뒤 num_ctx 8192로 올려 nvidia-smi 사용량(올리기 전과의 차이)과 /api/ps의 size_vram을 잰다
- 도구 호출: OpenAI 호환 /v1/chat/completions에 도구 1개를 주고 tool_calls가 오는지 본다
- 한글: "다음 영문 제목을 한 줄 한글로 요약" 3건, 선별: 큐레이터 선별 프롬프트로 20건 JSON 응답 시간
결과: tests/models/local_models.json. 모델 선택 근거는 docs/local-model.md에 표로 옮긴다.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

from agent import curator, schemas
from pipeline.validate import hangul_ratio

HERE = Path(__file__).parent
OLLAMA = "http://localhost:11434"
CANDIDATES = ["qwen3:8b", "llama3.1:8b", "gemma3:12b", "qwen3:14b"]
NUM_CTX = 8192
VRAM_LIMIT_MIB = 9 * 1024
TITLES = [
    "OpenAI adds structured outputs to the Realtime API for voice agents",
    "Hugging Face releases a small open-weight model that runs coding agents on a laptop",
    "n8n ships a native MCP client node so workflows can call external AI tools",
]
WEATHER_TOOL = {"type": "function", "function": {
    "name": "get_weather", "description": "도시의 현재 날씨를 조회한다",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}


def gpu_used_mib() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip().splitlines()[0])


def unload_all(client: httpx.Client) -> None:
    for running in client.get(f"{OLLAMA}/api/ps").json().get("models", []):
        client.post(f"{OLLAMA}/api/generate", json={"model": running["name"], "keep_alive": 0})
    for _ in range(30):
        if not client.get(f"{OLLAMA}/api/ps").json().get("models"):
            return
        time.sleep(1)


def chat(client: httpx.Client, model: str, prompt: str, *, fmt: str | None = None) -> dict:
    """네이티브 API. 사고 모델은 think=False로 끈다 (파이프라인과 같은 조건)."""
    body = {"model": model, "stream": False, "think": False, "options": {"num_ctx": NUM_CTX, "temperature": 0},
            "messages": [{"role": "user", "content": prompt}]}
    if fmt:
        body["format"] = fmt
    started = time.perf_counter()
    response = client.post(f"{OLLAMA}/api/chat", json=body)
    if response.status_code == 400 and "think" in response.text:  # 사고 기능이 없는 모델
        body.pop("think")
        response = client.post(f"{OLLAMA}/api/chat", json=body)
    response.raise_for_status()
    data = response.json()
    seconds = time.perf_counter() - started
    tps = data.get("eval_count", 0) / (data.get("eval_duration", 1) / 1e9)
    return {"text": data["message"]["content"].strip(), "seconds": round(seconds, 1), "tokens_per_sec": round(tps, 1)}


def tools_check(client: httpx.Client, model: str) -> dict:
    body = {"model": model, "temperature": 0, "tools": [WEATHER_TOOL], "reasoning_effort": "none",
            "messages": [{"role": "user", "content": "서울 날씨를 도구로 조회해줘"}]}
    response = client.post(f"{OLLAMA}/v1/chat/completions", json=body)
    if response.status_code != 200:
        return {"supported": False, "detail": response.text[:160]}
    calls = response.json()["choices"][0]["message"].get("tool_calls") or []
    return {"supported": bool(calls), "detail": calls[0]["function"] if calls else "tool_calls 없음"}


def selection_check(client: httpx.Client, model: str) -> dict:
    batch = [{"id": n, "type": "news", "source": "test", "title": f"{TITLES[n % 3]} (part {n})", "summary": ""}
             for n in range(1, 21)]
    result = chat(client, model, f"{curator.SELECT_PROMPT}\n\n<data>\n{json.dumps(batch, ensure_ascii=False)}\n</data>", fmt="json")
    try:
        parsed = schemas.SelectionBatch.model_validate_json(result["text"])
        valid = sorted(j.id for j in parsed.judgments) == list(range(1, 21))
    except ValueError:
        valid = False
    return {"seconds": result["seconds"], "tokens_per_sec": result["tokens_per_sec"], "json_valid_20": valid}


def measure(client: httpx.Client, model: str) -> dict:
    unload_all(client)
    baseline = gpu_used_mib()
    load = chat(client, model, "안녕이라고만 답해")
    loaded = gpu_used_mib()
    running = next(m for m in client.get(f"{OLLAMA}/api/ps").json()["models"] if m["name"] == model)
    korean = [chat(client, model, f"다음 영문 제목을 한 줄 한글로 요약해. 요약 한 줄만 써.\n{title}") for title in TITLES]
    row = {
        "model": model,
        "quantization": running.get("details", {}).get("quantization_level"),
        "context_length": running.get("context_length"),
        "vram_delta_mib": loaded - baseline,
        "vram_total_used_mib": loaded,
        "size_vram_mib": running.get("size_vram", 0) // 2**20,
        "size_mib": running.get("size", 0) // 2**20,
        "gpu_only": running.get("size_vram") == running.get("size"),
        "first_load_seconds": load["seconds"],
        "tools": tools_check(client, model),
        "korean": [{"title": t, "summary": k["text"], "hangul_ratio": round(hangul_ratio(k["text"]), 2), "seconds": k["seconds"]}
                   for t, k in zip(TITLES, korean)],
        "selection_20": selection_check(client, model),
    }
    row["within_limit"] = row["vram_delta_mib"] <= VRAM_LIMIT_MIB and row["gpu_only"]
    return row


def main() -> int:
    wanted = sys.argv[1:] or CANDIDATES
    with httpx.Client(timeout=300) as client:
        installed = {m["name"] for m in client.get(f"{OLLAMA}/api/tags").json()["models"]}
        rows = [measure(client, m) if m in installed else {"model": m, "missing": True} for m in wanted]
        unload_all(client)
    path = HERE / "local_models.json"
    previous = {r["model"]: r for r in json.loads(path.read_text(encoding="utf-8"))} if path.exists() else {}
    merged = previous | {r["model"]: r for r in rows}
    path.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(not r.get("missing") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
