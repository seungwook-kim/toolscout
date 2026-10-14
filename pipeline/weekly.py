"""금요일 메일 맨 아래 "이번 주 요약" 칸 (2026-09-27 사용자 결정 "추천대로": 따로 메일을 보내지 않고 금요일 브리핑에 붙인다).

모델을 부르지 않고 이번 주(오늘 포함 7일) 이 사용자에게 나간 카드에서 사실만 모은다. 지어낼 곳이 없다.
- 이번 주 큰 소식(headline 카드), 많이 받은 뉴스 주제 상위 3개, 샌드박스에서 설치해 본 MCP와 결과(분모는 원격 전용이 아닌 MCP), 새 버전이 나온 도구, 합계
- 카드가 한 장도 없으면 칸을 붙이지 않는다
- 모양(2026-10-14): 숫자 4칸(받은 카드·큰 소식·설치 성공·새 버전) + 묶음 목록. 표·색은 briefing_mail 것을 쓴다
"""
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import select

import db
from agent.schemas import TOPICS
from pipeline import verification
from pipeline.briefing_mail import INK, INK_2, MONO, MUTE, RP, SURFACE_2, _e, _url, box, section

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
    # 2026-10-15 2라운드: 분모는 원격 전용이 아닌 MCP, 분자는 그중 설치 단계 ok(verification.tool_counts, 웹·메일 도구 머리와 같은 셈)
    mcps = [card for _, card, _ in cards if card.get("type") == "mcp"]
    _, installed, local = verification.tool_counts(mcps)
    ok_titles = [c["title"] for c in mcps if verification.tool_counts([c])[1]]
    return {
        "since": since, "until": day, "days": len({d for d, _, _ in cards}), "cards": len(cards),
        "headlines": unique((card["title"], card["url"]) for _, card, _ in cards if card.get("headline")),
        "topics": [(TOPICS.get(t, t), n) for t, n in Counter(t for _, card, t in cards if card.get("type") == "news" and t).most_common(TOP_TOPICS)],
        "probed": local, "installed": installed, "installed_titles": ok_titles[:MAX_LIST],
        "updates": unique((card["title"], card["url"]) for _, card, _ in cards if (card.get("why_this_card") or "").startswith(UPDATE_PREFIX)),
    }


def _lines(s: dict) -> list[tuple[str, list[tuple[str, str | None]], bool]]:
    """(소제목, [(글, 링크)], 목록 점 여부) 묶음. html·text가 같은 내용을 쓴다. 빈 묶음은 뺀다."""
    out = []
    if s["headlines"]:
        out.append(("이번 주 큰 소식", [(title, url) for title, url in s["headlines"]], True))
    if s["topics"]:
        out.append(("많이 받은 뉴스 주제", [(" · ".join(f"{label} {n}장" for label, n in s["topics"]), None)], False))
    if s["probed"]:
        names = ", ".join(s["installed_titles"])
        out.append(("샌드박스에서 설치해 본 MCP", [(f"MCP {s['probed']}개 중 {s['installed']}개는 샌드박스 설치에 성공했어요"
                                                + (f" · {names}" if names else ""), None)], False))
    if s["updates"]:
        out.append(("새 버전이 나온 도구", [(title, url) for title, url in s["updates"]], True))
    return out


def block(user_id: int, day: date) -> dict | None:
    """금요일이 아니거나 이번 주 카드가 없으면 None. 반환: {html, text}. html은 메일 바깥 표의 행(tr)이라 꼬리 바로 위에 붙는다.
    모양(칸 머리·흰 카드·색)은 briefing_mail에서 가져다 쓴다(2026-10-14 2차 리디자인 3-7)."""
    if not is_summary_day(day):
        return None
    s = collect(user_id, day)
    if not s:
        return None
    period = f"{s['since'].month}/{s['since'].day}~{s['until'].month}/{s['until'].day} · {s['days']}일"
    stats = [(str(s["cards"]), "받은 카드"), (str(len(s["headlines"])), "큰 소식"),
             (f"{s['installed']}/{s['probed']}" if s["probed"] else "0", "설치 성공"), (str(len(s["updates"])), "새 버전")]
    cell = lambda n, label: (f'<td width="25%" align="center" style="width:25%;background-color:{SURFACE_2};border-radius:8px;padding:10px 4px">'  # noqa: E731
                             f'<b style="display:block;font-family:{MONO};font-size:20px;line-height:26px;color:{INK}">{_e(n)}</b>'
                             f'<span style="font-size:13px;line-height:18px;color:{MUTE}">{label}</span></td>')
    gap = '<td width="6" style="width:6px;font-size:0;line-height:0">&nbsp;</td>'
    parts = [f'<table {RP} width="100%"><tr>{gap.join(cell(n, label) for n, label in stats)}</tr></table>']
    text = [f"== {TITLE} ==", period, " · ".join(f"{label} {n}" for n, label in stats)]
    for n, (head, rows, dots) in enumerate(_lines(s)):
        items = "<br>".join(("· " if dots else "") + (f'<a href="{_e(_url(url))}" style="color:{INK_2}">{_e(t)}</a>' if _url(url) else _e(t))
                            for t, url in rows)
        parts.append(f'<p style="margin:{16 if n == 0 else 14}px 0 4px;font-size:14px;line-height:20px;font-weight:700;color:{INK}">{_e(head)}</p>'
                     f'<p style="margin:0;font-size:14px;line-height:22px;color:{INK_2}">{items}</p>')
        text += [head] + [f"  - {t}" + (f" <{url}>" if _url(url) else "") for t, url in rows]
    return {"html": section(TITLE, note=period) + box("".join(parts)), "text": "\n".join(text)}
