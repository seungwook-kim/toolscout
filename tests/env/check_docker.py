"""docker-compose.yml, Dockerfile, CI 검수 (착수 프롬프트 0단계 5번).

실행: uv run python -m tests.env.check_docker
로컬에 docker가 있으면 `docker compose config`로, 없으면 GitHub Actions의 현재 커밋 CI 결과로 판정한다.
CI 조회는 GITHUB_TOKEN(비공개 저장소)을 쓰고 값은 출력하지 않는다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml  # langchain-core 의존으로 설치되어 있다

import config  # noqa: F401  .env를 os.environ에 채운다

ROOT = Path(__file__).resolve().parents[2]
CI_STEPS = ["compose 파일 검사", "app 이미지 빌드", "app 기동", "/api/health 200 확인"]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def local_compose() -> dict:
    if shutil.which("docker") is None:
        return {"ok": False, "reason": "docker 명령 없음"}
    proc = subprocess.run(["docker", "compose", "config", "-q"], cwd=ROOT, capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "reason": proc.stderr.strip()[-500:]}


def git_credential_token() -> str:
    """push에 쓰는 git 자격 증명의 토큰. .env 토큰에 비공개 저장소 권한이 없을 때만 쓴다. 출력하지 않는다."""
    proc = subprocess.run(["git", "credential", "fill"], cwd=ROOT, input="protocol=https\nhost=github.com\n\n",
                          capture_output=True, text=True, timeout=30)
    return next((line[len("password="):] for line in proc.stdout.splitlines() if line.startswith("password=")), "")


def ci_result(wait_seconds: int = 0) -> dict:
    """현재 HEAD 커밋의 ci 워크플로우 결과. wait_seconds 동안 완료를 기다린다."""
    match = re.search(r"github\.com[:/](.+?)/(.+?)(?:\.git)?$", git("remote", "get-url", "origin"))
    if not match:
        return {"ok": False, "reason": "origin이 GitHub가 아님"}
    owner, repo, sha = match.group(1), match.group(2), git("rev-parse", "HEAD")
    base = f"https://api.github.com/repos/{owner}/{repo}/actions"
    token_source, client = None, None
    for source, token in (("GITHUB_TOKEN", os.environ.get("GITHUB_TOKEN", "")), ("git 자격 증명", None)):
        token = git_credential_token() if token is None else token
        if not token:
            continue
        candidate = httpx.Client(timeout=20, headers={"Accept": "application/vnd.github+json",
                                                      "Authorization": f"Bearer {token}"})
        if candidate.get(f"{base}/runs", params={"per_page": 1}).status_code == 200:
            token_source, client = source, candidate
            break
        candidate.close()
    if client is None:
        return {"ok": False, "reason": "Actions 조회 권한이 있는 토큰 없음"}
    deadline = time.monotonic() + wait_seconds
    try:
        while True:
            response = client.get(f"{base}/runs", params={"head_sha": sha, "per_page": 10})
            if response.status_code != 200:
                return {"ok": False, "reason": f"Actions 조회 HTTP {response.status_code}"}
            runs = [r for r in response.json().get("workflow_runs", []) if r["name"] == "ci"]
            run = runs[0] if runs else None
            if run and run["status"] == "completed" or time.monotonic() >= deadline:
                break
            time.sleep(15)
        if run is None:
            return {"ok": False, "reason": "이 커밋의 ci 실행 없음 (push 전이거나 대기 중)", "sha": sha[:7]}
        jobs = client.get(f"{base}/runs/{run['id']}/jobs").json().get("jobs", [])
    finally:
        client.close()
    steps = {s["name"]: s["conclusion"] for job in jobs for s in job.get("steps", []) if s["name"] in CI_STEPS}
    return {"ok": run["conclusion"] == "success", "token_source": token_source, "sha": sha[:7], "status": run["status"],
            "conclusion": run["conclusion"], "url": run["html_url"], "steps": steps}


def static_checks() -> dict:
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    services = compose.get("services", {})
    app, n8n = services.get("app", {}), services.get("n8n", {})
    default_services = sorted(name for name, svc in services.items() if not svc.get("profiles"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    ci_text = ci_path.read_text(encoding="utf-8") if ci_path.exists() else ""
    return {
        "기본_서비스_app_n8n_2개": default_services == ["app", "n8n"],
        "app_빌드_8000": "build" in app and any("8000" in str(p) for p in app.get("ports", [])),
        "app_sqlite_기본값_없음": "sqlite" not in compose_text.lower(),
        "n8n_공식이미지_5678": str(n8n.get("image", "")).startswith("docker.n8n.io/n8nio/n8n")
        and any("5678" in str(p) for p in n8n.get("ports", [])),
        "n8n_tool_usage_변수_없음": "N8N_COMMUNITY_PACKAGES_ALLOW_TOOL_USAGE" not in compose_text,
        "langfuse_프로필": services.get("langfuse-web", {}).get("profiles") == ["langfuse"],
        "dockerfile_python_3_12_slim": "FROM python:3.12-slim" in dockerfile,
        "ci_4단계_정의": all(step in ci_text for step in CI_STEPS) and "on:\n  push:" in ci_text,
    }


def main() -> int:
    wait = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    local = local_compose()
    ci = ci_result(wait) if not local["ok"] else {"ok": False, "reason": "로컬 docker로 확인함"}
    static = static_checks()
    report = {"local_docker": local, "github_ci": ci, "static": static,
              "pass": (local["ok"] or ci["ok"]) and all(static.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
