"""아침 브리핑 메일 본문 (계획안 부록 B 6 "이메일은 카드 전체", 예외 처리 표, 뼈대 완성 정의 "카드마다 trace_id").

- 뉴스·도구 칸을 나눈다. 도구 카드가 없으면 "오늘 새 도구 없음", 빈 행(empty_reason)이면 "오늘 볼 만한 게 없었음"
- 카드: 제목(원문 링크), 요약, 나한테는, 이 카드인 이유, 장점·단점(근거 링크), 설치 명령(도구), 원문 확인 필요, trace_id
- 외부 텍스트(기사 제목, 모델 출력)는 모두 HTML 이스케이프한다. 링크는 http(s)만 쓴다
- HTML과 같은 내용의 텍스트 본문을 함께 만든다
- 피드백 버튼(W3, 부록 C): links(card, 버튼)가 있으면 카드마다 서명 링크 버튼. 뉴스는 관심없음·이상함, 도구는 써봤음까지 셋
- 검증 결과(세션 8): MCP는 "직접 깔아봤더니" 4단계, 스킬은 "SKILL.md 읽어봤더니" 위험 신호. 두 고정 문구는 결과가 없어도 늘 붙인다
- combine(day, sections): 개발 모드에서 프로필 여러 개의 브리핑을 한 통으로 묶는다 (운영 모드는 사용자마다 render 한 통)
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
MCP_SCOPE = "도구가 올바르게 동작하는지는 범위 밖입니다."  # 부록 D 5, 카드 템플릿 고정
SKILL_SCOPE = "안전 보증이 아니라 위험 신호 표시입니다."  # 부록 D 스킬 3, 카드 템플릿 고정
STEP_KEYS = ("install", "run", "tools_list", "auth_required")
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


def verify_lines(card: dict) -> list[str]:
    """도구 카드의 검증 결과 줄 (HTML·텍스트 공용 원문, 이스케이프 전)."""
    if card.get("type") == "mcp":
        verification = card.get("verification") or {}
        steps = " / ".join((verification.get(k) or {}).get("label", "") for k in STEP_KEYS if verification.get(k))
        head = f"직접 깔아봤더니: {steps}" if steps else f"직접 깔아봤더니: {card.get('verification_note') or '검증 예정'}"
        return [head, MCP_SCOPE]
    if card.get("type") == "skill":
        risk = card.get("risk_signal") or {}
        if not risk:
            return [f"SKILL.md 읽어봤더니: {card.get('verification_note') or '판독 예정'}", SKILL_SCOPE]
        quote = f" \"{risk['quote']}\"" if risk.get("quote") else ""
        return [f"SKILL.md 읽어봤더니: 위험 신호 {risk.get('label', '')}{quote}", SKILL_SCOPE]
    return []


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
    for n, line in enumerate(verify_lines(card)):
        style = "margin:8px 0 0;font-size:13px" if n == 0 else "margin:2px 0 0;color:#777;font-size:12px"
        parts.append(f'<p style="{style}">{_e(line)}</p>')
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
    lines += [f"  {line}" for line in verify_lines(card)]
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


def combine_subject(day: date, sections: list[dict]) -> str:
    when = f"{day.month}월 {day.day}일"
    cards = sum(s["cards"] for s in sections)
    return f"[개발 모드] {when} AI 브리핑 · 프로필 {len(sections)}개 · 카드 {cards}장"


def combine(day: date, sections: list[dict]) -> dict:
    """개발 모드 묶음 메일 (2026-09-16 사용자 결정: 프로필마다 한 통이 아니라 다 합쳐 한 통).

    sections: [{role, cards, html, text}] (render 결과에 프로필 이름·카드 수를 더한 것, 발송함 순서)
    반환: {subject, html, text}. 맨 위에 프로필 목차, 아래에 프로필별 구역.
    """
    heads = [f"프로필 {s['role']} · 카드 {s['cards']}장" for s in sections]
    toc = "".join(f"<li>{_e(head)}</li>" for head in heads)
    body = "".join(f'<hr style="border:0;border-top:1px solid #ddd;margin:24px 0">'
                   f'<h1 style="font-size:16px;margin:0 0 12px">{_e(head)}</h1>{section["html"]}'
                   for head, section in zip(heads, sections))
    page = (f'<div style="font-family:-apple-system,\'Segoe UI\',\'Malgun Gothic\',sans-serif;max-width:640px;margin:0 auto;color:#111">'
            f'<p style="margin:0 0 4px">개발 모드 묶음 메일</p>'
            f'<p style="color:#999;font-size:13px;margin:0 0 8px">가짜·테스트 프로필 {len(sections)}개의 브리핑을 한 통에 담았습니다.</p>'
            f'<ul style="color:#555;font-size:13px;margin:0 0 8px">{toc}</ul>{body}</div>')
    text = ("개발 모드 묶음 메일\n"
            f"가짜·테스트 프로필 {len(sections)}개의 브리핑을 한 통에 담았습니다.\n"
            + "\n".join(f"- {head}" for head in heads) + "\n\n"
            + "\n\n".join(f"{'=' * 40}\n{head}\n{'=' * 40}\n{section['text']}" for head, section in zip(heads, sections)))
    return {"subject": combine_subject(day, sections), "html": page, "text": text}
