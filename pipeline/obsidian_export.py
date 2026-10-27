"""그날 메일에 나간 MCP·스킬을 옵시디언 vault의 `mcp-skills/mcp/`·`mcp-skills/skill/` 폴더에 도구 하나당 노트 한 개로 쌓는다 (2026-10-27 사용자 요청).

실행: uv run python -m pipeline.obsidian_export [--day YYYY-MM-DD] [--days N]   (기본: 오늘과 어제, 켜지는 PC를 놓친 날을 따라잡음)
vault 위치는 환경변수 OBSIDIAN_VAULT, 없으면 C:\\Users\\Wook\\Documents\\ObsidianVault. 운영 DB를 읽기만 하고 vault 파일만 쓴다.
- 대상: briefings.sent_at이 찍힌 카드의 MCP·스킬(데모 제외). 사용자 수와 상관없이 도구당 노트 하나, 발송일만 늘어난다 (다시 돌려도 같은 결과)
- 내용: 요약, 확인 결과, 좋은 점·아쉬운 점, 설치 명령, 링크. 사용자별 글(for_me)과 사용자 정보는 넣지 않는다. 기사 본문은 없다
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

import db
from agent.schemas import TOPICS
from pipeline.run_daily import KST

DEFAULT_VAULT = r"C:\Users\Wook\Documents\ObsidianVault"
FOLDERS = {"mcp": "mcp-skills/mcp", "skill": "mcp-skills/skill"}
ROOT_HUB = "mcp-skills/MCP·스킬 모음"
HUBS = {"mcp": "mcp-skills/mcp/MCP 모음", "skill": "mcp-skills/skill/스킬 모음"}
GRAPH_GROUPS = [("path:mcp-skills/mcp", 5017087), ("path:mcp-skills/skill", 16752451),  # 그래프 뷰 색: MCP 파랑, 스킬 주황
                ("path:mcp-skills/주제", 5025616), ("path:mcp-skills/출처", 10066329)]  # 주제 초록, 출처 회색
WEEKDAYS = "월화수목금토일"
UNSAFE = re.compile(r'[\\/:*?"<>|#^\[\]]')


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
        sent: dict[int, set] = {}
        for item_id, sent_day in s.execute(select(db.Briefing.item_id, db.Briefing.date).where(
                db.Briefing.item_id.in_(list(tools)), db.Briefing.sent_at.is_not(None)).distinct()).all():
            sent.setdefault(item_id, set()).add(sent_day)
        for item_id, entry in tools.items():
            entry["dates"] = sorted(sent.get(item_id, {day}))
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


def group_hubs(item) -> list[tuple[str, str]]:
    """도구가 링크를 거는 묶음 노트 [(vault 기준 경로, 이름)]. 종류(MCP·스킬 모음), 주제, 출처 순."""
    hubs = [(HUBS[item.type], Path(HUBS[item.type]).name)]
    topic = TOPICS.get(getattr(item, "topic", None) or "")
    if topic:
        hubs.append((f"mcp-skills/주제/{topic}", topic))
    source = UNSAFE.sub(" ", getattr(item, "source", None) or "").strip()
    if source:
        hubs.append((f"mcp-skills/출처/{source}", source))
    return hubs


def render(item, card: dict, dates: list[date], uses: list[str] | None = None) -> str:
    """노트 본문. 속성, 요약 콜아웃, 확인 결과 표, 좋은 점·아쉬운 점, 설치 명령. HTML은 쓰지 않는다."""
    summary = (card.get("summary_ko") or item.summary_ko or "").strip()
    lines = ["---", f"type: {item.type}", f"title: \"{item.title.replace(chr(34), chr(39))}\"", f"url: {item.url}", f"source: {item.source}"]
    if item.version:
        lines.append(f"version: {item.version}")
    if item.stars is not None:
        lines.append(f"stars: {item.stars}")
    lines += ["발송일:", *[f"  - {d}" for d in dates], "tags: [toolscout]", "---", "", f"# {item.title}", "",
              f"> [!summary] 한 줄 요약\n> {summary or '요약 없음'}", "", f"원문: {item.url}", "묶음: " + " · ".join(f"[[{path}|{name}]]" for path, name in group_hubs(item)), ""]
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


def write_hubs(vault: Path, items=()) -> None:
    """그래프 뷰에서 한 덩어리로 보이게 하는 묶음 노트. 도구 노트가 종류·주제·출처 묶음으로 링크를 걸고, 묶음은 전체 모음으로 이어진다.
    주제·출처 묶음은 items에 나온 것만 만든다."""
    notes = {ROOT_HUB: f"# MCP·스킬 모음\n\n- [[{HUBS['mcp']}|MCP 모음]]\n- [[{HUBS['skill']}|스킬 모음]]\n"}
    for kind, hub in HUBS.items():
        kind_name = "MCP" if kind == "mcp" else "스킬"
        notes[hub] = (f"# {Path(hub).name}\n\n상위: [[{ROOT_HUB}|MCP·스킬 모음]]\n\n"
                      f"{kind_name} 노트가 이 노트로 링크를 걸어 그래프 뷰에서 한 묶음으로 보인다. 도구는 날짜(요일) 폴더에 있다.\n")
    for item in items:
        for hub, name in group_hubs(item)[1:]:
            group = "주제" if "/주제/" in hub else "출처"
            notes[hub] = f"# {name}\n\n상위: [[{ROOT_HUB}|MCP·스킬 모음]]\n\n같은 {group}의 도구 노트가 이 노트로 링크를 건다.\n"
    for name, text in notes.items():
        path = vault / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def ensure_graph_colors(vault: Path) -> None:
    """그래프 뷰 색 묶음 두 개를 없을 때만 더한다. 사용자가 이미 둔 설정은 그대로 둔다."""
    path = vault / ".obsidian" / "graph.json"
    if not path.exists():
        return
    config = json.loads(path.read_text(encoding="utf-8"))
    groups = config.setdefault("colorGroups", [])
    have = {g.get("query") for g in groups}
    groups += [{"query": q, "color": {"a": 1, "rgb": rgb}} for q, rgb in GRAPH_GROUPS if q not in have]
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def export_day(day: date, vault: Path | None = None) -> dict:
    """반환: {date, tools, written}. 같은 날 다시 돌려도 같은 파일을 같은 내용으로 덮어쓴다."""
    vault = vault or vault_dir()
    tools = collect(day)
    write_hubs(vault, [entry["item"] for entry in tools])
    ensure_graph_colors(vault)
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
