"""폴더 문서 규칙 검수 (폴더 문서 규칙, 착수 프롬프트 0단계 1번).

실행: uv run python -m tests.docs.check_folder_docs
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ["agent", "sources", "pipeline", "routes", "mcp", "n8n", "web", "tests", "docs"]
ENTRY = re.compile(r"^- \d{4}-\d{2}-\d{2} · .+ · .+ · .+$")
EM_DASH = "—"


def check_folder(name: str) -> dict:
    readme = ROOT / name / "README.md"
    changelog = ROOT / name / "CHANGELOG.md"
    result = {"folder": name, "readme": readme.exists(), "changelog": changelog.exists()}
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        result["readme_lines"] = len(text.splitlines())
        result["todo_section"] = "\n## 할 일\n" in text
        result["readme_ok"] = result["readme_lines"] <= 30 and EM_DASH not in text and result["todo_section"]
    if changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        entries = [line for line in text.splitlines() if line.startswith("- ")]
        result["changelog_ok"] = bool(entries) and ENTRY.match(entries[0]) is not None and EM_DASH not in text
    result["pass"] = bool(result.get("readme_ok") and result.get("changelog_ok"))
    return result


def main() -> int:
    folders = [check_folder(name) for name in FOLDERS]
    root_changelog = ROOT / "CHANGELOG.md"
    root_ok = root_changelog.exists() and "- 세션 1" in root_changelog.read_text(encoding="utf-8")
    plan_ok = (ROOT / "docs" / "계획안.md").exists()
    report = {
        "folders": folders,
        "root_changelog": root_ok,
        "plan_in_docs": plan_ok,
        "pass": all(f["pass"] for f in folders) and root_ok and plan_ok,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
