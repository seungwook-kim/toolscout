"""금요일 "이번 주 요약" 칸 검수 (2026-09-27). 모델·네트워크를 쓰지 않고 DB는 읽기만 한다.

실행: uv run python -m tests.pipeline.check_weekly
- 금요일에만 붙고, 이번 주(오늘 포함 7일) 카드가 없으면 붙지 않는다
- 합계·큰 소식·많이 받은 뉴스 주제·샌드박스에서 설치해 본 MCP·새 버전 도구를 카드 데이터에서만 모은다(모델 호출 없음)
- 메일 html·text 맨 아래에 붙고, 요약이 없으면 메일은 그대로. 링크는 안전한 주소만
실측(9/25 금 기준 본인 계정): 9/19~9/25 · 7일 · 카드 46장, 큰 소식 1, 주제 상위 3, 설치 3개 중 2개 성공
"""
import json
import sys
from datetime import date

from pipeline import briefing_mail, weekly

FRIDAY, SUNDAY = date(2026, 9, 25), date(2026, 9, 27)


def remote_only() -> bool:
    """원격 전용 MCP(설치 해당없음·주소 명령)는 분모에 넣지 않는다. 미검증 MCP는 분모에 든다(2026-10-15 2라운드, verification.tool_counts)."""
    import db
    from sqlalchemy import select

    original = db.get_engine

    class Rows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, *a): return Rows([
            (FRIDAY, {"type": "mcp", "title": "원격", "url": "https://r.test", "verification": {"install": {"status": "na", "label": "설치 해당없음"}}}, "mcp_tools"),
            (FRIDAY, {"type": "mcp", "title": "원격 주소", "url": "https://r2.test", "install_cmd": "https://mcp.r2.test/mcp"}, "mcp_tools"),
            (FRIDAY, {"type": "mcp", "title": "설치됨", "url": "https://i.test", "verification": {"install": {"status": "ok"}}}, "mcp_tools"),
            (FRIDAY, {"type": "mcp", "title": "실패", "url": "https://f.test", "verification": {"install": {"status": "bad"}}}, "mcp_tools"),
            (FRIDAY, {"type": "mcp", "title": "미검증", "url": "https://u.test", "install_cmd": "npx -y u"}, "mcp_tools")])

    db.get_engine = lambda: type("E", (), {"connect": lambda self: Conn()})()
    try:
        s = weekly.collect(1, FRIDAY)
    finally:
        db.get_engine = original
    return s["probed"] == 3 and s["installed"] == 1 and s["installed_titles"] == ["설치됨"]


def main() -> int:
    real = weekly.collect(45, FRIDAY)
    block = weekly.block(45, FRIDAY)
    card = {"type": "news", "title": "t", "url": "https://a.test/x", "summary_ko": "요약입니다.", "for_me": "쓸모가 있습니다.",
            "why_this_card": "이유", "relevance": 4, "trace_id": "abc", "pros": [], "cons": []}
    plain = briefing_mail.render(FRIDAY, "개발자", [card])
    with_week = briefing_mail.render(FRIDAY, "개발자", [card], weekly=block)
    fake = {"since": date(2026, 9, 19), "until": FRIDAY, "days": 1, "cards": 1, "headlines": [("큰 소식", "javascript:alert(1)")],
            "topics": [], "probed": 2, "installed": 1, "installed_titles": ["One"], "updates": [("One 1.4.0", "https://github.com/a/one")]}
    original = weekly.collect
    weekly.collect = lambda uid, day: fake
    try:
        unsafe = weekly.block(1, FRIDAY)
    finally:
        weekly.collect = original
    checks = {
        "금요일에만": weekly.is_summary_day(FRIDAY) and not weekly.is_summary_day(SUNDAY) and weekly.block(45, SUNDAY) is None,
        "이번주_카드_없으면_안붙음": weekly.block(45, date(2000, 1, 7)) is None,
        "실제DB_합계·기간": real is not None and real["since"] == date(2026, 9, 19) and real["cards"] > 0 and 1 <= real["days"] <= 7,
        "실제DB_주제는_뉴스만·상위3": real is not None and len(real["topics"]) <= weekly.TOP_TOPICS and all(n > 0 for _, n in real["topics"]),
        "실제DB_설치성공은_설치해본_수_이하": real is not None and real["installed"] <= real["probed"],
        # 2026-10-14: 텍스트 칸 머리는 "== 이름 ==", preheader에도 "이번 주 요약 포함"이 있어 칸 위치는 마지막 등장으로 본다
        "메일_맨아래에_붙음": block is not None and with_week["text"].rstrip().endswith("원문 링크를 확인하세요.")
        and "== 이번 주 요약 ==" in with_week["text"] and with_week["html"].rindex("이번 주 요약") > with_week["html"].rindex("새 MCP·스킬")
        and with_week["html"].rindex("이번 주 요약") < with_week["html"].index("AI에게 질문하기"),
        "요약_없으면_메일_그대로": plain["html"] == briefing_mail.render(FRIDAY, "개발자", [card], weekly=None)["html"]
        and "이번 주 요약" not in plain["html"],
        "안전하지_않은_링크는_글자만": unsafe is not None and "javascript:" not in unsafe["html"] and 'href="https://github.com/a/one"' in unsafe["html"],
        "새버전_도구_칸": unsafe is not None and "새 버전이 나온 도구" in unsafe["text"],
        "설치수는_원격전용(해당없음)_제외": remote_only(),
        # 2026-10-15 2라운드 3장 4절: 머리 "샌드박스에서 설치해 본 MCP", 문장은 브랜드 pipe 문장과 같은 셈법·낱말
        "MCP_줄_낱말": unsafe is not None and "샌드박스에서 설치해 본 MCP" in unsafe["html"] and "직접 설치해 본" not in unsafe["html"]
        and "MCP 2개 중 1개는 샌드박스 설치에 성공했어요 · One" in unsafe["text"],
    }
    report = {"checks": checks, "real": {k: str(v) if isinstance(v, date) else v for k, v in (real or {}).items()}, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
