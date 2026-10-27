"""옵시디언 내보내기(pipeline/obsidian_export.py) 검수 (2026-10-27). DB·모델·네트워크를 쓰지 않고 가짜 도구와 임시 폴더로 확인한다.

실행: uv run python -m tests.pipeline.check_obsidian_export
- 도구마다 노트 하나, 처음 나간 날의 `날짜 (요일)` 폴더 아래 mcp-skills/mcp/·mcp-skills/skill/로 갈린다 / 며칠 나가도 노트는 하나, 발송일만 늘어남
- 노트에 요약·이럴 때 쓰면 좋다·확인 결과·좋은 점·아쉬운 점·설치가 들어가고 HTML과 사용자 정보는 없음
- 제목에 못 쓰는 글자는 바뀌고, 제목이 같은 다른 도구는 번호를 붙여 덮어쓰지 않음 / 같은 입력을 다시 돌려도 같은 결과
"""
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pipeline import obsidian_export as ox

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과  " if ok else "실패  ") + name)


def tool(item_id: int, kind: str, title: str, url: str) -> SimpleNamespace:
    return SimpleNamespace(id=item_id, type=kind, title=title, url=url, source="github_search", version="1.2.0", stars=115,
                           summary_ko="Canvas 강의 정보를 묻는 MCP 서버입니다.")


CARD = {"summary_ko": "Canvas 강의 정보를 묻는 MCP 서버입니다.", "install_cmd": "npx canvas-mcp",
        "pros": [{"text": "읽기 전용", "evidence_url": "https://example.com/e"}], "cons": [{"text": "토큰 필요", "evidence_url": None}],
        "risk_signal": {"label": "확인 필요"}, "verification_note": "다음 날 06:00 검증 예정",
        "verification": {"install": {"label": "설치 성공 14.0s", "status": "ok"}, "tools_list": {"label": "도구 6개", "status": "ok"},
                         "probed_at": "10-26 22:14 샌드박스"}}


def write(vault: Path, item, dates: list[date], uses: list[str]) -> Path:
    path = ox.note_path(vault, item, dates[0])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ox.render(item, CARD, dates, uses), encoding="utf-8")
    return path


with tempfile.TemporaryDirectory() as tmp:
    vault = Path(tmp)
    mcp, skill = tool(1, "mcp", "canvas-mcp (a/b)", "https://github.com/a/canvas"), tool(2, "skill", "nlm-skill", "https://github.com/a/nlm")
    d1, d2 = date(2026, 10, 26), date(2026, 10, 27)
    first = write(vault, mcp, [d1], ["MCP 설계를 참고할 때", "읽기 전용 도구를 고를 때"])
    second = write(vault, mcp, [d1, d2], ["MCP 설계를 참고할 때"])
    skill_path = write(vault, skill, [d2], [])
    check("MCP는 mcp-skills/mcp/날짜 (요일)/, 스킬은 mcp-skills/skill/ 아래", first.parent == vault / "mcp-skills" / "mcp" / "2026-10-26 (월)" and skill_path.parent == vault / "mcp-skills" / "skill" / "2026-10-27 (화)")
    check("며칠 나가도 노트는 하나(처음 나간 날 폴더)", first == second and len(list((vault / "mcp-skills" / "mcp").rglob("*.md"))) == 1)
    text = second.read_text(encoding="utf-8")
    check("발송일이 늘어남", "  - 2026-10-26" in text and "  - 2026-10-27" in text)
    check("요약·쓰면 좋은 때·확인·좋은 점·아쉬운 점·설치", all(s in text for s in (
        "[!summary]", "## 이럴 때 쓰면 좋다", "| 설치 | 설치 성공 14.0s |", "## 좋은 점", "## 아쉬운 점", "npx canvas-mcp", "위험 신호: 확인 필요")))
    check("HTML과 사용자 정보 없음", "<" not in text and "user" not in text.lower().replace("url", ""))
    check("제목의 못 쓰는 글자 제거", "/" not in first.name and first.name == "canvas-mcp (a b).md")
    other = tool(9, "mcp", "canvas-mcp (a/b)", "https://github.com/other/canvas")
    clash = ox.note_path(vault, other, d1)
    check("제목만 같은 다른 도구는 번호를 붙임", clash.name == "canvas-mcp (a b) (9).md" and clash != first)
    check("다시 돌려도 같은 내용", write(vault, mcp, [d1, d2], ["MCP 설계를 참고할 때"]).read_text(encoding="utf-8") == text)

failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} 통과")
sys.exit(1 if failed else 0)
