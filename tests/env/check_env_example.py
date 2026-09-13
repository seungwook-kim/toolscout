""".env.example 키 목록과 .env 무시 검수 (착수 프롬프트 0단계 4번).

실행: uv run python -m tests.env.check_env_example
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = [
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "E2B_API_KEY", "GITHUB_TOKEN", "SKILLSMP_API_KEY",
    "SUPABASE_URL", "SUPABASE_KEY", "DATABASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
    "GMAIL_USER", "GMAIL_APP_PASSWORD", "MCP_SERVICE_KEY", "SESSION_SECRET", "DAILY_QUESTION_LIMIT",
    "DAILY_PROBE_LIMIT", "ADMIN_EMAILS",
]
DEFAULTS = {"DAILY_QUESTION_LIMIT": "10", "DAILY_PROBE_LIMIT": "3"}


def main() -> int:
    pairs = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            pairs[name.strip()] = value.strip()
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT, capture_output=True).returncode == 0
    checks = {
        "키_목록_일치": list(pairs) == KEYS,
        "값은_비움_기본값_2개만": all(pairs.get(k, "") == DEFAULTS.get(k, "") for k in KEYS),
        "env_gitignore": ignored,
        "env_추적안됨": not tracked,
    }
    report = {"keys": len(pairs), "checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
