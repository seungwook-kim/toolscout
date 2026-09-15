"""아침 브리핑 메일 본문 (계획안 부록 B 6 "이메일은 카드 전체", 예외 처리 표, 뼈대 완성 정의 "카드마다 trace_id").

- 뉴스·도구 칸을 나눈다. 도구 카드가 없으면 "오늘 새 도구 없음", 빈 행(empty_reason)이면 "오늘 볼 만한 게 없었음"
- 카드: 제목(원문 링크), 요약, 나한테는, 이 카드인 이유, 장점·단점(근거 링크), 설치 명령(도구), 원문 확인 필요, trace_id
- 외부 텍스트(기사 제목, 모델 출력)는 모두 HTML 이스케이프한다. 링크는 http(s)만 쓴다
- HTML과 같은 내용의 텍스트 본문을 함께 만든다
- 피드백 버튼(W3, 부록 C): links(card, 버튼)가 있으면 카드마다 서명 링크 버튼. 뉴스는 관심없음·이상함, 도구는 써봤음까지 셋
"""
import html
import re
from datetime import date
from typing import Callable

TOOL_TYPES = ("mcp", "skill")
SAFE_URL = re.compile(r"^https?://[^\s\"'<>]+$")
NO_TOOLS = "오늘 새 도구 없음"
RELATED_TITLE = "이번 주 관련 MCP·스킬"  # 월요일 관련 카드(F3-b)
EMPTY_TITLE = "오늘 볼 만한 게 없었음"
Links = Callable[[dict, str], str]


def actions_for(card: dict) -> list[str]:
    return ["써봤음", "관심없음", "이상함"] if card.get("type") in TOOL_TYPES else ["관심없음", "이상함"]


def _url(value: str | None) -> str | None:
    return value if value and SAFE_URL.match(value) else None


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


def subject(day: date, cards: list[dict], empty_reason: str | None) -> str:
    when = f"{day.month}월 {day.day}일"
    return f"[toolscout] {when} AI 브리핑 · {EMPTY_TITLE}" if not cards else f"[toolscout] {when} AI 브리핑 · 카드 {len(cards)}장"


def _points_html(label: str, points: list[dict]) -> str:
    if not points:
        return ""
    rows = "".join(
        f'<li>{_e(p.get("text"))}' + (f' <a href="{_e(_url(p.get("evidence_url")))}" style="color:#555">근거</a>'
                                     if _url(p.get("evidence_url")) else "") + "</li>"
        for p in points)
    return f'<p style="margin:8px 0 2px;font-weight:600">{label}</p><ul style="margin:0;padding-left:18px">{rows}</ul>'


def _card_html(card: dict, links: Links | None = None) -> str:
    link = _url(card.get("url"))
    title = f'<a href="{_e(link)}" style="color:#111;text-decoration:none">{_e(card.get("title"))}</a>' if link else _e(card.get("title"))
    parts = [f'<h3 style="margin:0 0 6px;font-size:16px">{title}</h3>']
    if card.get("notice"):
        parts.append(f'<p style="margin:0 0 6px;color:#b45309;font-size:12px">{_e(card["notice"])}</p>')
    parts.append(f'<p style="margin:0 0 8px">{_e(card.get("summary_ko"))}</p>')
    parts.append(f'<p style="margin:0 0 8px;background:#f3f4f6;padding:8px;border-radius:6px"><b>나한테는</b> {_e(card.get("for_me"))}</p>')
    parts.append(f'<p style="margin:0;color:#555;font-size:13px">이 카드인 이유: {_e(card.get("why_this_card"))}</p>')
    parts.append(_points_html("장점", card.get("pros") or []))
    parts.append(_points_html("단점", card.get("cons") or []))
    if card.get("install_cmd") and card.get("type") in TOOL_TYPES:
        parts.append(f'<p style="margin:8px 0 0;font-size:13px">설치: <code>{_e(card["install_cmd"])}</code></p>')
    if links and card.get("item_id"):
        buttons = "".join(f'<a href="{_e(links(card, action))}" style="display:inline-block;margin:8px 6px 0 0;padding:4px 10px;'
                          f'border:1px solid #d1d5db;border-radius:6px;color:#111;text-decoration:none;font-size:13px">{action}</a>'
                          for action in actions_for(card))
        parts.append(f"<div>{buttons}</div>")
    parts.append(f'<p style="margin:8px 0 0;color:#999;font-size:11px">trace_id {_e(card.get("trace_id"))}</p>')
    return f'<div style="border:1px solid #e5e7eb;border-radius:8px;padding:14px;margin:0 0 12px">{"".join(parts)}</div>'


def _card_text(card: dict, links: Links | None = None) -> str:
    lines = [f"■ {card.get('title', '')}", f"  {card.get('url', '')}"]
    if card.get("notice"):
        lines.append(f"  ({card['notice']})")
    lines += [f"  {card.get('summary_ko', '')}", f"  나한테는: {card.get('for_me', '')}", f"  이 카드인 이유: {card.get('why_this_card', '')}"]
    for label, key in (("장점", "pros"), ("단점", "cons")):
        for point in card.get(key) or []:
            lines.append(f"  {label}: {point.get('text', '')} ({point.get('evidence_url', '')})")
    if card.get("install_cmd") and card.get("type") in TOOL_TYPES:
        lines.append(f"  설치: {card['install_cmd']}")
    if links and card.get("item_id"):
        lines += [f"  [{action}] {links(card, action)}" for action in actions_for(card)]
    lines.append(f"  trace_id {card.get('trace_id', '')}")
    return "\n".join(lines)


def render(day: date, role: str, cards: list[dict], empty_reason: str | None = None, links: Links | None = None) -> dict:
    """반환: {subject, html, text}. cards는 순위 순서의 card_json."""
    news = [c for c in cards if c.get("type") not in TOOL_TYPES]
    tools = [c for c in cards if c.get("type") in TOOL_TYPES and not c.get("related")]
    related = [c for c in cards if c.get("related")]
    head = f"{day.year}년 {day.month}월 {day.day}일 · {role} 기준"
    if not cards:
        body_html = (f'<h2 style="font-size:18px">{EMPTY_TITLE}</h2>'
                     f'<p style="color:#555">{_e(empty_reason or "오늘 보여줄 항목이 없다")}</p>')
        body_text = f"{EMPTY_TITLE}\n{empty_reason or '오늘 보여줄 항목이 없다'}"
    else:
        body_html = ('<h2 style="font-size:18px;margin:16px 0 8px">뉴스</h2>' + ("".join(_card_html(c, links) for c in news) or "<p>오늘 뉴스 카드 없음</p>")
                     + '<h2 style="font-size:18px;margin:16px 0 8px">새 MCP·스킬</h2>'
                     + ("".join(_card_html(c, links) for c in tools) or f'<p style="color:#555">{NO_TOOLS}</p>')
                     + (f'<h2 style="font-size:18px;margin:16px 0 8px">{RELATED_TITLE}</h2>' + "".join(_card_html(c, links) for c in related)
                        if related else ""))
        body_text = ("[뉴스]\n" + ("\n\n".join(_card_text(c, links) for c in news) or "오늘 뉴스 카드 없음")
                     + "\n\n[새 MCP·스킬]\n" + ("\n\n".join(_card_text(c, links) for c in tools) or NO_TOOLS)
                     + (f"\n\n[{RELATED_TITLE}]\n" + "\n\n".join(_card_text(c, links) for c in related) if related else ""))
    page = (f'<div style="font-family:-apple-system,\'Segoe UI\',\'Malgun Gothic\',sans-serif;max-width:640px;margin:0 auto;'
            f'color:#111;line-height:1.55"><p style="color:#555;margin:0 0 4px">toolscout 아침 브리핑</p>'
            f'<p style="color:#999;font-size:13px;margin:0 0 12px">{_e(head)}</p>{body_html}'
            f'<p style="color:#999;font-size:11px;margin-top:20px">요약은 원문을 바탕으로 AI가 썼습니다. 중요한 결정 전에는 원문 링크를 확인하세요.</p></div>')
    text = (f"toolscout 아침 브리핑\n{head}\n\n{body_text}\n\n"
            "요약은 원문을 바탕으로 AI가 썼습니다. 중요한 결정 전에는 원문 링크를 확인하세요.")
    return {"subject": subject(day, cards, empty_reason), "html": page, "text": text}
