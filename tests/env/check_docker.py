"""docker-compose.yml, Dockerfile 검수 (착수 프롬프트 0단계 5번).

실행: uv run python -m tests.env.check_docker
통과 조건은 `docker compose config`가 실제로 성공하는 것이다. 정적 검사는 참고용이다.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml  # langchain-core 의존으로 설치되어 있다

ROOT = Path(__file__).resolve().parents[2]


def compose_config() -> dict:
    if shutil.which("docker") is None:
        return {"ok": False, "reason": "docker 명령 없음"}
    proc = subprocess.run(["docker", "compose", "config", "-q"], cwd=ROOT, capture_output=True, text=True)
    return {"ok": proc.returncode == 0, "reason": proc.stderr.strip()[-500:]}


def static_checks() -> dict:
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)
    services = compose.get("services", {})
    app, n8n = services.get("app", {}), services.get("n8n", {})
    default_services = sorted(name for name, svc in services.items() if not svc.get("profiles"))
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    return {
        "기본_서비스_app_n8n_2개": default_services == ["app", "n8n"],
        "app_빌드_8000": "build" in app and any("8000" in str(p) for p in app.get("ports", [])),
        "n8n_공식이미지_5678": str(n8n.get("image", "")).startswith("docker.n8n.io/n8nio/n8n")
        and any("5678" in str(p) for p in n8n.get("ports", [])),
        "n8n_tool_usage_변수_없음": "N8N_COMMUNITY_PACKAGES_ALLOW_TOOL_USAGE" not in compose_text,
        "langfuse_프로필": services.get("langfuse-web", {}).get("profiles") == ["langfuse"],
        "dockerfile_python_3_12_slim": "FROM python:3.12-slim" in dockerfile,
    }


def main() -> int:
    config = compose_config()
    static = static_checks()
    report = {"docker_compose_config": config, "static": static, "pass": config["ok"] and all(static.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
