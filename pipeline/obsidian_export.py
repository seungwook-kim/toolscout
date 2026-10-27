"""그날 메일에 나간 MCP·스킬을 옵시디언 vault의 `MCP/`·`스킬/` 폴더에 도구 하나당 노트 한 개로 쌓는다 (2026-10-27 사용자 요청).

실행: uv run python -m pipeline.obsidian_export [--day YYYY-MM-DD] [--days N]   (기본: 오늘과 어제, 켜지는 PC를 놓친 날을 따라잡음)
vault 위치는 환경변수 OBSIDIAN_VAULT, 없으면 C:\\Users\\Wook\\Documents\\ObsidianVault. 운영 DB를 읽기만 하고 vault 파일만 쓴다.
- 대상: briefings.sent_at이 찍힌 카드의 MCP·스킬(데모 제외). 사용자 수와 상관없이 도구당 노트 하나, 발송일만 늘어난다 (다시 돌려도 같은 결과)
- 내용: 요약, 확인 결과, 좋은 점·아쉬운 점, 설치 명령, 링크. 사용자별 글(for_me)과 사용자 정보는 넣지 않는다. 기사 본문은 없다
"""
import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

import db
from pipeline.run_daily import KST

DEFAULT_VAULT = r"C:\Users\Wook\Documents\ObsidianVault"
FOLDERS = {"mcp": "MCP", "skill": "스킬"}
WEEKDAYS = "월화수목금토일"
UNSAFE =re.compile(r'[\\/:*?"<>|#^\[\]]')


def vault_dir() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT") or DEFAULT_VAULT)


def collect(day: date) -> list[dict]:
    """그날 발송된 MCP·스킬을 도구별로 모은다. 카드 내용은 같은 도구의 첫 카드(사용자 번호 순)를 쓴다."""
    with db.session() as s:
        rows = s.exec(
            select(db.Item, db.Briefing.card_json, db.Briefing.user_id)
            .join(db.Briefing, db.Briefing.item_id == db.Item.id).join(db.User, db.User.id == db.Briefing.user_id)
            .where(db.Briefing.date == day, db.Briefing.sent_at.is_not(None), db.User.is_demo == False,  # noqa: E712
                   db.Item.type.in_(list(FOLDERS))).order_by(db.Briefing.user_id)).all()
        tools: dict[int, dict] = {}
        for item, card, _ in rows:
            entry = tools.setdefault(item.id, {"item": item, "card": card or {}, "uses": []})
            use = ((card or {}).get("for_me") or "").strip()
            if use and use not in entry["uses"]:
                entry["uses"].append(use)
        for entry in tools.values():
            dates = s.execute(select(db.Briefing.date).where(db.Briefing.item_id == entry["item"].id,
                                                             db.Briefing.sent_at.is_not(None)).distinct()).scalars().all()
            entry["dates"] = sorted(dates)
        return list(tools.values())


def _bullets(points) -> list[str]:
    out = []
    for point in points or []:
        text = point.get("text") if isinstance(point, dict) else str(point)
        url = point.get("evidence_url") if isinstance(point, dict) else None
        if text:
            out.append(f"- {text}" + (f" ([근거]({url}))" if url else ""))
    return out


def _check_rows(verification) -> list[str]:
    if not isinstance(verification, dict):
        return []
    names = {"install": "설치", "run": "실행", "tools_list": "도구 목록", "auth_required": "인증"}
    rows = [f"| {names[k]} | {v.get('label', '')} |" for k, v in verification.items() if k in names and isinstance(v, dict)]
    return (["| 항목 | 결과 |", "|---|---|", *rows] + ([f"\n검증: {verification['probed_at']}"] if verification.get("probed_at") else [])) if rows else []


def render(item, card: dict, dates: list[date], uses: list[str] | None = None) -> str:
    """노트 본문. 속성, 요약 콜아웃, 확인 결과 표, 좋은 점·아쉬운 점, 설치 명령. HTML은 쓰지 않는다."""
    summary = (card.get("summary_ko") or item.summary_ko or "").strip()
    lines = ["---", f"type: {item.type}", f"title: \"{item.title.replace(chr(34), chr(39))}\"", f"url: {item.url}", f"source: {item.source}"]
    if item.version:
        lines.append(f"version: {item.version}")
    if item.stars is not None:
        lines.append(f"stars: {item.stars}")
    lines += ["발송일:", *[f"  - {d}" for d in dates], "tags: [toolscout]", "---", "", f"# {item.title}", "",
              f"> [!summary] 한 줄 요약\n> {summary or '요약 없음'}", "", f"원문: {item.url}", ""]
    if uses:
        lines += ["## 이럴 때 쓰면 좋다", "", *[f"- {use}" for use in uses[:3]], ""]
    checks = _check_rows(card.get("verification"))
    risk = card.get("risk_signal")
    if checks or isinstance(risk, dict):
        lines += ["## 확인 결과", ""]
        if isinstance(risk, dict) and risk.get("label"):
            lines += [f"- 위험 신호: {risk['label']}", ""]
        lines += checks + [""] if checks else []
    if card.get("verification_note"):
        lines += [f"- {card['verification_note']}", ""]
    for heading, key in (("좋은 점", "pros"), ("아쉬운 점", "cons")):
        bullets = _bullets(card.get(key))
        if bullets:
            lines += [f"## {heading}", "", *bullets, ""]
    if card.get("install_cmd"):
        lines += ["## 설치", "", "```bash", str(card["install_cmd"]).strip(), "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def note_path(vault: Path, item, first_day: date) -> Path:
    """도구 하나는 노트 하나. 처음 나간 날 폴더(`2026-10-27 (화)`)에 둔다. 이후 날은 같은 노트의 발송일만 늘어난다."""
    folder = vault / FOLDERS[item.type] / f"{first_day} ({WEEKDAYS[first_day.weekday()]})"
    name = UNSAFE.sub(" ", item.title).strip()[:80] or f"item-{item.id}"
    path = folder / f"{name}.md"
    if path.exists() and f"url: {item.url}\n" not in path.read_text(encoding="utf-8"):  # 제목이 같은 다른 도구
        path = folder / f"{name} ({item.id}).md"
    return path


def export_day(day: date, vault: Path | None = None) -> dict:
    """반환: {date, tools, written}. 같은 날 다시 돌려도 같은 파일을 같은 내용으로 덮어쓴다."""
    vault = vault or vault_dir()
    tools = collect(day)
    for entry in tools:
        path = note_path(vault, entry["item"], entry["dates"][0])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(entry["item"], entry["card"], entry["dates"], entry["uses"]), encoding="utf-8")
    return {"date": str(day), "tools": len(tools), "written": len(tools)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", help="YYYY-MM-DD (없으면 오늘부터 거꾸로 --days일)")
    parser.add_argument("--days", type=int, default=2)
    args = parser.parse_args(argv)
    today = datetime.now(KST).date()
    days = [date.fromisoformat(args.day)] if args.day else [today - timedelta(days=n) for n in range(args.days)][::-1]
    if not vault_dir().is_dir():
        print("vault 폴더를 찾을 수 없음 (OBSIDIAN_VAULT 확인)")
        return 1
    for day in days:
        print(export_day(day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
