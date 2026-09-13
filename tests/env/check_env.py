"""설치 환경 검사 (착수 프롬프트 0단계 3번, 계획안 8장 마지막 줄).

실행: uv run python -m tests.env.check_env
결과: tests/env/check_env.json
"""
import importlib
import importlib.metadata as md
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).with_name("check_env.json")
MUST_IMPORT = ["langchain_core", "mcp", "anthropic", "google.genai", "langfuse", "e2b", "feedparser", "sqlmodel"]
MUST_FAIL = ["langgraph", "langchain"]


def pip_cmd(*args: str) -> tuple[str, list[str]]:
    """venv에 pip이 있으면 pip, 없으면 uv pip으로 같은 명령을 돌린다."""
    has_pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode == 0
    if has_pip:
        return "pip", [sys.executable, "-m", "pip", *args]
    uv = shutil.which("uv")
    if uv is None:
        return "none", []
    return "uv pip", [uv, "pip", *args, "--python", sys.executable]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def try_import(name: str) -> dict:
    try:
        module = importlib.import_module(name)
        return {"ok": True, "file": getattr(module, "__file__", None)}
    except ImportError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    tool, cmd = pip_cmd("check")
    check = run(cmd) if cmd else None
    tool_show, cmd_show = pip_cmd("show", "langchain-core")
    show = run(cmd_show) if cmd_show else None
    requires_line = next((ln for ln in (show.stdout if show else "").splitlines() if ln.startswith("Requires:")), "")
    requires = [r.strip() for r in requires_line.removeprefix("Requires:").split(",") if r.strip()]

    imports = {name: try_import(name) for name in MUST_IMPORT}
    failures = {name: try_import(name) for name in MUST_FAIL}

    from mcp.server import MCPServer  # noqa: F401  mcp SDK 2.x 확인용

    checks = {
        "python_3_12": sys.version_info[:2] == (3, 12),
        "pip_check_pass": bool(check) and check.returncode == 0,
        "import_langgraph_ImportError": not failures["langgraph"]["ok"],
        "import_langchain_ImportError": not failures["langchain"]["ok"],
        "import_langchain_core_ok": imports["langchain_core"]["ok"],
        "langchain_core_requires_no_langgraph": bool(requires) and not any("langgraph" in r for r in requires),
        "required_imports_ok": all(v["ok"] for v in imports.values()),
        "mcp_sdk_2x": md.version("mcp").startswith("2."),
        # 루트 mcp/ 폴더가 설치된 SDK를 가리지 않는지
        "mcp_not_shadowed": "site-packages" in (imports["mcp"].get("file") or ""),
    }
    mcp_file = imports["mcp"].get("file") or ""
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python_version": sys.version.split()[0],
        "pip_check": {"tool": tool, "returncode": check.returncode if check else None,
                      "output": (check.stdout + check.stderr).strip() if check else ""},
        "langchain_core": {"tool": tool_show, "version": md.version("langchain-core"), "requires": requires},
        "imports": {name: {"ok": v["ok"], "version": _version(name)} for name, v in imports.items()},
        "must_fail": {name: v for name, v in failures.items()},
        "mcp_module_file": mcp_file[mcp_file.find("site-packages"):].replace("\\", "/"),
        "checks": checks,
        "pass": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


def _version(module_name: str) -> str | None:
    dist = {"langchain_core": "langchain-core", "google.genai": "google-genai"}.get(module_name, module_name)
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


if __name__ == "__main__":
    sys.exit(main())
