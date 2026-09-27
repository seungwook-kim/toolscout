"""루트 README 사양 검수 (착수 프롬프트 0단계 2번).

실행: uv run python -m tests.docs.check_readme
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = [
    "무엇을 하나", "왜 만들었나", "어떻게 동작하나", "에이전트 3개", "기술 스택", "빠른 시작",
    "내 브리핑을 Claude Code에서 쓰기", "프로젝트 구조", "품질 지표", "스크린샷",
]
BADGES = ["Python-3.12", "FastAPI", "MCP", "Supabase", "Langfuse"]
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿]")
FLOW_WORDS = ["예약", "큐레이터", "검증관", "해설가", "발송", "되돌림", "기억", "Claude Code", "공개 MCP"]


def quality_rows(text: str) -> list[list[str]]:
    """README "품질 지표" 표의 본문 줄(머리·구분선 제외)을 칸 목록으로."""
    section = text.split("## 📊 품질 지표", 1)[-1].split("\n## ", 1)[0]
    rows = [line.strip().strip("|").split("|") for line in section.splitlines() if line.strip().startswith("|")]
    return [[c.strip() for c in r] for r in rows[2:]]


def tree_block(text: str, marker: str) -> str | None:
    """marker 뒤 첫 번째 toolscout/ 트리 코드 블록."""
    if marker not in text:
        return None
    match = re.search(r"```text\n(toolscout/\n.*?)```", text[text.index(marker):], re.S)
    return match.group(1) if match else None


def main() -> int:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    headings = [line for line in lines if line.startswith("## ")]
    body = [line for line in lines if not line.startswith("#")]
    mermaid = re.search(r"```mermaid\n(.*?)```", text, re.S)
    badge_lines = [line for line in lines if "img.shields.io/badge/" in line]
    checks = {
        "제목_toolscout": lines[0] == "# toolscout",
        "배지_5개": len(badge_lines) == 5 and all(any(b in line for line in badge_lines) for b in BADGES),
        "절_모두_존재": all(any(s in h for h in headings) for s in SECTIONS),
        "mermaid_흐름": bool(mermaid) and all(w in mermaid.group(1) for w in FLOW_WORDS),
        "되돌림_2개": bool(mermaid) and mermaid.group(1).count("되돌림") == 2,
        "뉴스·MCP_카드": "[뉴스]" in text and "[MCP]" in text and all(n in text for n in "①②③④"),
        "빠른시작_4단계": all(k in text for k in [".env.example", "docker compose up", "첫 브리핑"]),
        "MCP_설정_JSON": '"mcpServers"' in text and '"headers"' in text,
        # 처음엔 14줄 모두 측정예정이었다. 실측이 채워지면(9/27 선별·발송·트레이스) 칸이 비지 않았는지만 본다
        "품질지표_14줄_실측또는_측정예정": len(quality_rows(text)) >= 14 and all(len(r) == 4 and all(r) for r in quality_rows(text)),
        "스크린샷_4개": text.count("docs/img/") >= 5,
        "라이선스·설계문서·작성자": all(k in text for k in ["MIT", "docs/계획안.md", "작성자"]),
        "긴_줄표_없음": "—" not in text,
        "이모지_본문에_없음": not any(EMOJI.search(line) for line in body),
        "이모지_절당_1개_이하": all(len(EMOJI.findall(h)) <= 1 for h in headings),
        "300줄_이하": len(lines) <= 300,
        "계획안_부록F_트리와_동일": tree_block(text, "프로젝트 구조") == tree_block(
            (ROOT / "docs" / "계획안.md").read_text(encoding="utf-8"), "## 부록 F"),
    }
    report = {"lines": len(lines), "checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
