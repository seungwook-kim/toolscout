"""메일 가독성 검수 (2026-09-22). 네트워크·DB를 쓰지 않는다.

왜: 카드 하나가 화면 한 장을 넘고, 제목·요약·장단점이 같은 무게였다. 장점·단점마다 붙던 "근거" 링크는
전부 원문과 같은 주소였고, 묶음 메일은 프로필 구역마다 "toolscout 아침 브리핑" 머리를 되풀이했다.

실행: uv run python -m tests.pipeline.check_mail_layout
- 근거 링크는 원문과 다를 때만 (HTML·텍스트 같은 규칙)
- 메일은 사용자마다 한 통이고 머리 하나다(개발 모드 묶음 메일은 2026-09-28에 없앰). 빈 행 메일도 같은 머리
- 요일 표기, 종류 칩(뉴스는 출처 도메인), 색은 웹앱 디자인 기준과 같은 값
"""
import json
import sys
from datetime import date
from pathlib import Path

from pipeline import briefing_mail as mail

DAY = date(2026, 9, 22)
URL = "https://www.aitimes.com/news/articleView.html?idxno=1"
OTHER = "https://github.com/example/repo"
DESIGN = Path(__file__).resolve().parents[2] / "docs" / "design-reference.html"


def card(**over) -> dict:
    return {"type": "news", "title": "검수 뉴스", "url": URL, "summary_ko": "요약", "for_me": "나에게", "why_this_card": "이유",
            "pros": [{"text": "같은 근거", "evidence_url": URL}, {"text": "다른 근거", "evidence_url": OTHER}],
            "cons": [], "trace_id": "t-1", "item_id": 1} | over


def main() -> int:
    single = mail.render(DAY, "개발자", [card(), card(type="mcp", title="검수 MCP", url=OTHER, pros=[], trace_id="t-2")])
    empty = mail.render(DAY, "마케터", [], "후보 없음")
    html, text = single["html"], single["text"]
    design = DESIGN.read_text(encoding="utf-8")

    checks = {
        "근거_원문과_같으면_안붙음": html.count(">근거</a>") == 1,
        "근거_원문과_다르면_붙음": f'href="{OTHER}"' in html and ">근거</a>" in html,
        "텍스트도_같은_근거_규칙": f"같은 근거 ({URL})" not in text and f"다른 근거 ({OTHER})" in text,
        "요일_표기": "9월 22일 화요일" in html and "9월 22일 화요일" in empty["html"],
        "뉴스_칩에_출처_도메인": "뉴스 · aitimes.com" in html,
        "도구_칩은_종류만": ">MCP</div>" in html,
        "단독_메일은_머리_하나": html.count("TOOLSCOUT 아침 브리핑") == 1,
        "빈행_메일도_머리_하나·이유": empty["html"].count("TOOLSCOUT 아침 브리핑") == 1 and "후보 없음" in empty["html"],
        "개발모드_표시_없음": "개발 모드" not in html + empty["html"] + single["subject"] + empty["subject"],
        "render가_body를_돌려줌": "body" in single and "TOOLSCOUT" not in single["body"],
        "카드마다_trace_id": html.count("trace_id t-") == 2,
        "색이_웹앱_디자인과_같음": all(v.lower() in design.lower() for v in (mail.INK, mail.ACCENT, mail.PAPER, mail.LINE, mail.MUTE)),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
