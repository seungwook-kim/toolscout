"""받아 본 도구의 새 버전 알림 (2026-09-27 사용자 결정, "써봤음" 기록이 0건이라 범위를 받아 본 도구로 넓힘).

- 대상: 최근 SHOWN_DAYS일 안에 이 사용자에게 카드로 나간 MCP. 카드 제목 끝의 버전(레지스트리 표시 제목 "이름 버전")이 그때 버전이다.
  스킬은 버전이 없어 뺀다
- 새 버전: 오늘 MCP 레지스트리 수집이 받은 "7일 안에 갱신된 서버" 전체(SourceResult.versions)에서 같은 저장소의 최신 버전.
  수집 단계는 버전 업을 별 50 이상·상위 10건만 남기므로 그 전 목록을 쓴다. API를 더 부르지 않는다
- 사용자당 하루 PER_DAY장, 가장 최근에 나온 것. 도구 칸 맨 앞에 넣고 이유는 "받아 본 도구의 새 버전 (a → b)".
  해설가는 GitHub 릴리스 페이지를 읽고(source_url), 발송 전 검증은 새 버전을 다시 설치해 본다(update_from)
- 새 버전 카드가 나가면 그 제목이 새 버전이 되므로 다음 날 같은 알림이 되풀이되지 않는다
"""
import re
from datetime import date, timedelta

from sqlalchemy import select

import db

SHOWN_DAYS, PER_DAY = 30, 1
VERSION = re.compile(r"^v?\d+(?:\.\d+)*(?:[-+.][0-9A-Za-z.]+)?$")


def version_in_title(title: str) -> str | None:
    last = (title or "").rsplit(" ", 1)[-1]
    return last if " " in (title or "") and VERSION.match(last) else None


def _key(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version.split("-")[0].split("+")[0])[:4])


def is_newer(new: str | None, old: str | None) -> bool:
    """숫자 부분으로 비교한다. 숫자를 못 읽으면 다르기만 해도 새 버전으로 본다."""
    if not new or not old or new.lstrip("v") == old.lstrip("v"):
        return False
    a, b = _key(new.lstrip("v")), _key(old.lstrip("v"))
    return a > b if a and b else True


def shown_versions(user_id: int, today: date) -> dict[str, dict]:
    """{url: {version, title, topic}} 최근 SHOWN_DAYS일 이 사용자의 MCP 카드. 같은 도구는 가장 최근 카드. 오늘 것은 뺀다(재실행 멱등)."""
    since = today - timedelta(days=SHOWN_DAYS)
    with db.get_engine().connect() as c:
        rows = c.execute(select(db.Briefing.date, db.Briefing.card_json, db.Item.topic).join(db.Item, db.Item.id == db.Briefing.item_id)
                         .where(db.Briefing.user_id == user_id, db.Briefing.date >= since, db.Briefing.date < today,
                                db.Item.type == "mcp").order_by(db.Briefing.date, db.Briefing.id)).all()
    out = {}
    for _, card, topic in rows:
        version = version_in_title(card.get("title", ""))
        if version:
            out[card["url"]] = {"version": version, "title": card["title"], "topic": topic}
    return out


def pick(shown: dict[str, dict], latest: dict[str, dict]) -> list[dict]:
    """새 버전 카드 후보(가장 최근에 나온 순으로 PER_DAY장)."""
    found = []
    for url, before in shown.items():
        now = latest.get(url)
        if now and is_newer(now.get("version"), before["version"]):
            found.append((now.get("published") or "", url, before, now))
    found.sort(reverse=True)
    return [item(url, before, now) for _, url, before, now in found[:PER_DAY]]


def item(url: str, before: dict, now: dict) -> dict:
    old, new = before["version"], now["version"]
    return {"type": "mcp", "title": now["title"], "url": url, "source": "mcp_registry", "topic": before.get("topic") or "mcp_tools",
            "summary": f"{old}에서 {new}로 새 버전이 나왔습니다. {now.get('summary', '')}".strip(), "install": now.get("install"),
            "source_url": f"{url.rstrip('/')}/releases", "update_from": old,
            "why": f"받아 본 도구의 새 버전 ({old} → {new})", "published_at": now.get("published")}


def add_to_plans(plans: list[dict], latest: dict[str, dict], today: date, shown_for=shown_versions) -> int:
    """사용자 plan마다 새 버전 카드를 도구 칸 맨 앞에 넣는다. 오늘 이미 고른 도구와 겹치면 넣지 않는다. 반환: 넣은 수."""
    if not latest:
        return 0
    added = 0
    for plan in plans:
        if plan.get("failed"):
            continue
        chosen = {i["url"] for key in ("news", "tools", "related") for i in plan.get(key, [])}
        updates = [u for u in pick(shown_for(plan["user_id"], today), latest) if u["url"] not in chosen]
        if updates:
            plan["tools"] = updates + plan["tools"]
            plan["empty"], plan["empty_reason"] = False, None
            added += len(updates)
    return added
