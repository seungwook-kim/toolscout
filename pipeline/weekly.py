"""금요일 메일 맨 아래 "이번 주 요약" 칸 (2026-09-27 사용자 결정 "추천대로": 따로 메일을 보내지 않고 금요일 브리핑에 붙인다).

모델을 부르지 않고 이번 주(오늘 포함 7일) 이 사용자에게 나간 카드에서 사실만 모은다. 지어낼 곳이 없다.
- 이번 주 큰 소식(headline 카드), 많이 받은 뉴스 주제 상위 3개, 직접 설치해 본 MCP와 결과, 새 버전이 나온 도구, 합계
- 카드가 한 장도 없으면 칸을 붙이지 않는다
"""
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select

import db
from agent.schemas import TOPICS
from pipeline.briefing_mail import INK2, LINE, MUTE, _e, _section, _url

SUMMARY_WEEKDAY = 4  # 금요일
DAYS, TOP_TOPICS, MAX_LIST = 7, 3, 5
TITLE = "이번 주 요약"
UPDATE_PREFIX = "받아 본 도구의 새 버전"


def is_summary_day(day: date) -> bool:
    return day.weekday() == SUMMARY_WEEKDAY


def collect(user_id: int, day: date) -> dict | None:
    since = day - timedelta(days=DAYS - 1)
    with db.get_engine().connect() as c:
        rows = c.execute(select(db.Briefing.date, db.Briefing.card_json, db.Item.topic).join(db.Item, db.Item.id == db.Briefing.item_id)
                         .where(db.Briefing.user_id == user_id, db.Briefing.date >= since, db.Briefing.date <= day)
                         .order_by(db.Briefing.date, db.Briefing.rank)).all()
    if not rows:
        return None
    cards = [(d, card, topic) for d, card, topic in rows if card]
    unique = lambda items: list({title: (title, url) for title, url in items}.values())[:MAX_LIST]  # noqa: E731
    # 원격 전용 MCP는 설치 단계가 없다(해당없음). 설치를 실제로 해 본 것만 센다
    probed = [(card["title"], status) for _, card, _ in cards if card.get("type") == "mcp" and card.get("verification")
              and (status := (card["verification"].get("install") or {}).get("status")) in ("ok", "bad")]
    return {
        "since": since, "until": day, "days": len({d for d, _, _ in cards}), "cards": len(cards),
        "headlines": unique((card["title"], card["url"]) for _, card, _ in cards if card.get("headline")),
        "topics": [(TOPICS.get(t, t), n) for t, n in Counter(t for _, card, t in cards if card.get("type") == "news" and t).most_common(TOP_TOPICS)],
        "probed": len(probed), "installed": sum(status == "ok" for _, status in probed),
        "installed_titles": [t for t, status in probed if status == "ok"][:MAX_LIST],
        "updates": unique((card["title"], card["url"]) for _, card, _ in cards if (card.get("why_this_card") or "").startswith(UPDATE_PREFIX)),
    }


def _lines(s: dict) -> list[tuple[str, list[tuple[str, str | None]]]]:
    """(소제목, [(글, 링크)]) 묶음. html·text가 같은 내용을 쓴다."""
    out = [("합계", [(f"{s['since'].month}/{s['since'].day}~{s['until'].month}/{s['until'].day} · {s['days']}일 · 카드 {s['cards']}장", None)])]
    if s["headlines"]:
        out.append(("큰 소식", [(title, url) for title, url in s["headlines"]]))
    if s["topics"]:
        out.append(("많이 받은 뉴스 주제", [(" · ".join(f"{label} {n}장" for label, n in s["topics"]), None)]))
    if s["probed"]:
        out.append(("직접 설치해 본 MCP", [(f"{s['probed']}개 중 {s['installed']}개 설치 성공", None)]
                    + [(title, None) for title in s["installed_titles"]]))
    if s["updates"]:
        out.append(("새 버전이 나온 도구", [(title, url) for title, url in s["updates"]]))
    return out


def block(user_id: int, day: date) -> dict | None:
    """금요일이 아니거나 이번 주 카드가 없으면 None. 반환: {html, text}."""
    if not is_summary_day(day):
        return None
    s = collect(user_id, day)
    if not s:
        return None
    parts, text = [], [f"[{TITLE}]"]
    for head, rows in _lines(s):
        items = "".join(f'<div style="margin:2px 0">&middot; ' + (f'<a href="{_e(_url(url))}" style="color:{INK2}">{_e(t)}</a>' if _url(url) else _e(t))
                        + "</div>" for t, url in rows)
        parts.append(f'<div style="margin:10px 0 0"><div style="font-size:11px;font-weight:700;color:{MUTE}">{_e(head)}</div>{items}</div>')
        text += [f"{head}"] + [f"  - {t}" + (f" {url}" if url else "") for t, url in rows]
    html = (_section(TITLE) + f'<div style="background:#FFFFFF;border:1px solid {LINE};border-radius:10px;padding:14px 18px;'
            f'font-size:14px;color:{INK2}">{"".join(parts)}</div>')
    return {"html": html, "text": "\n".join(text)}
