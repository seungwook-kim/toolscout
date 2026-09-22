"""아침 브리핑 메일 본문 (계획안 부록 B 6 "이메일은 카드 전체", 예외 처리 표, 뼈대 완성 정의 "카드마다 trace_id").

- 뉴스·도구 칸을 나눈다. 도구 카드가 없으면 "오늘 새 도구 없음", 빈 행(empty_reason)이면 "오늘 볼 만한 게 없었음"
- 카드: 제목(원문 링크), 요약, 나한테는, 이 카드인 이유, 장점·단점(근거 링크), 설치 명령(도구), 원문 확인 필요, trace_id
- 외부 텍스트(기사 제목, 모델 출력)는 모두 HTML 이스케이프한다. 링크는 http(s)만 쓴다
- HTML과 같은 내용의 텍스트 본문을 함께 만든다
- 피드백 버튼(W3, 부록 C): links(card, 버튼)가 있으면 카드마다 서명 링크 버튼. 뉴스는 관심없음·이상함, 도구는 써봤음까지 셋
- 검증 결과(세션 8): MCP는 "직접 깔아봤더니" 4단계, 스킬은 "SKILL.md 읽어봤더니" 위험 신호. 두 고정 문구는 결과가 없어도 늘 붙인다
- combine(day, sections): 개발 모드에서 프로필 여러 개의 브리핑을 한 통으로 묶는다 (운영 모드는 사용자마다 render 한 통)
- 모양(2026-09-22): 색은 웹앱 docs/design-reference.html 토큰 값을 그대로 쓴다(메일은 CSS 변수를 못 쓴다).
  카드는 종류 칩, 제목, 요약, 나한테는 순으로 무게를 줄이고, 장점·단점의 근거 링크는 원문과 다를 때만 붙인다
"""
import html
import re
from datetime import date
from typing import Callable
from urllib.parse import urlsplit

TOOL_TYPES = ("mcp", "skill")
SAFE_URL = re.compile(r"^https?://[^\s\"'<>]+$")
NO_TOOLS = "오늘 새 도구 없음"
RELATED_TITLE = "이번 주 관련 MCP·스킬"  # 월요일 관련 카드(F3-b)
EMPTY_TITLE = "오늘 볼 만한 게 없었음"
MCP_SCOPE = "도구가 올바르게 동작하는지는 범위 밖입니다."  # 부록 D 5, 카드 템플릿 고정
SKILL_SCOPE = "안전 보증이 아니라 위험 신호 표시입니다."  # 부록 D 스킬 3, 카드 템플릿 고정
STEP_KEYS = ("install", "run", "tools_list", "auth_required")
Links = Callable[[dict, str], str]

INK, INK2, MUTE, LINE, PAPER = "#15181E", "#3F434B", "#7A7E86", "#E1E2DD", "#F7F7F4"
ACCENT, ACCENT_INK, ACCENT_WASH, OK, WARN, WARN_WASH = "#12766A", "#0C5B51", "#E3F0ED", "#1E7B4E", "#A85E08", "#FBEFDF"
MAST, MAST_TEXT, MAST_MUTE = "#15181E", "#E9EAE6", "#9DA2AC"
KIND = {"news": ("뉴스", "#4C5FD5"), "mcp": ("MCP", "#12766A"), "skill": ("스킬", "#7B4BC7")}
FONT = "-apple-system,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif"
WEEKDAYS = "월화수목금토일"


def actions_for(card: dict) -> list[str]:
    return ["써봤음", "관심없음", "이상함"] if card.get("type") in TOOL_TYPES else ["관심없음", "이상함"]


def _url(value: str | None) -> str | None:
    return value if value and SAFE_URL.match(value) else None


def _e(value) -> str:
    return html.escape(str(value or ""), quote=True)


def subject(day: date, cards: list[dict], empty_reason: str | None) -> str:
    when = f"{day.month}월 {day.day}일"
    return f"[toolscout] {when} AI 브리핑 · {EMPTY_TITLE}" if not cards else f"[toolscout] {when} AI 브리핑 · 카드 {len(cards)}장"


def _host(url: str | None) -> str:
    host = (urlsplit(url).hostname or "") if _url(url) else ""
    return host[4:] if host.startswith("www.") else host


def _points_html(label: str, points: list[dict], card_url: str | None, sign: str, color: str) -> str:
    """장점·단점 한 묶음. 근거 링크는 입력 항목 링크만 쓰므로 대개 원문과 같다. 원문과 다를 때만 붙인다."""
    if not points:
        return ""
    rows = []
    for point in points:
        evidence = _url(point.get("evidence_url"))
        tail = (f' <a href="{_e(evidence)}" style="color:{MUTE};font-size:12px">근거</a>'
                if evidence and evidence != _url(card_url) else "")
        rows.append(f'<div style="padding-left:14px;text-indent:-14px;margin:2px 0">'
                    f'<span style="color:{color};font-weight:700">{sign}</span> {_e(point.get("text"))}{tail}</div>')
    return (f'<div style="margin:12px 0 0;font-size:13px;color:{INK2};line-height:1.55">'
            f'<div style="font-size:11px;font-weight:700;color:{color};letter-spacing:.04em;margin:0 0 2px">{label}</div>'
            f'{"".join(rows)}</div>')


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
    label, color = KIND.get(card.get("type") or "news", KIND["news"])
    host = _host(link)
    chip = f"{label} · {host}" if host and card.get("type") not in TOOL_TYPES else label
    parts = [f'<div style="font-size:11px;font-weight:700;color:{color};letter-spacing:.04em;margin:0 0 6px">{_e(chip)}</div>']
    title = _e(card.get("title"))
    if link:
        title = (f'<a href="{_e(link)}" style="color:{INK};text-decoration:none">{title}'
                 f'<span style="color:{MUTE};font-weight:400"> &#8599;</span></a>')
    parts.append(f'<h3 style="margin:0 0 8px;font-size:17px;line-height:1.4;font-weight:700;color:{INK}">{title}</h3>')
    if card.get("notice"):
        parts.append(f'<div style="display:inline-block;margin:0 0 8px;padding:2px 8px;border-radius:4px;background:{WARN_WASH};'
                     f'color:{WARN};font-size:12px">{_e(card["notice"])}</div>')
    parts.append(f'<p style="margin:0 0 12px;font-size:15px;line-height:1.65;color:{INK2}">{_e(card.get("summary_ko"))}</p>')
    parts.append(f'<div style="margin:0;padding:10px 12px;border-left:3px solid {ACCENT};background:{ACCENT_WASH};'
                 f'font-size:14px;line-height:1.6;color:{INK}"><b style="color:{ACCENT_INK}">나한테는</b> {_e(card.get("for_me"))}</div>')
    if card.get("why_this_card"):
        parts.append(f'<p style="margin:8px 0 0;font-size:12px;line-height:1.5;color:{MUTE}">'
                     f'이 카드인 이유 · {_e(card["why_this_card"])}</p>')
    parts.append(_points_html("장점", card.get("pros") or [], link, "+", OK))
    parts.append(_points_html("단점", card.get("cons") or [], link, "&minus;", WARN))
    if card.get("install_cmd") and card.get("type") in TOOL_TYPES:
        parts.append(f'<div style="margin:12px 0 0;font-size:12px;color:{MUTE}">설치:</div>'
                     f'<div style="margin:3px 0 0;padding:8px 10px;background:{PAPER};border:1px solid {LINE};border-radius:6px;'
                     f'font-family:Consolas,Menlo,monospace;font-size:12px;color:{INK};word-break:break-all">{_e(card["install_cmd"])}</div>')
    for n, line in enumerate(verify_lines(card)):
        style = f"margin:12px 0 0;font-size:13px;color:{INK2}" if n == 0 else f"margin:2px 0 0;font-size:11px;color:{MUTE}"
        parts.append(f'<p style="{style}">{_e(line)}</p>')
    if links and card.get("item_id"):
        buttons = "".join(f'<a href="{_e(links(card, action))}" style="display:inline-block;margin:0 6px 0 0;padding:4px 12px;'
                          f'border:1px solid {LINE};border-radius:999px;color:{INK2};text-decoration:none;font-size:12px">{action}</a>'
                          for action in actions_for(card))
        parts.append(f'<div style="margin:14px 0 0">{buttons}</div>')
    parts.append(f'<p style="margin:10px 0 0;color:#B5B8BE;font-size:10px">trace_id {_e(card.get("trace_id"))}</p>')
    return (f'<div style="background:#FFFFFF;border:1px solid {LINE};border-radius:10px;padding:18px 18px 14px;margin:0 0 12px">'
            f'{"".join(parts)}</div>')


def _card_text(card: dict, links: Links | None = None) -> str:
    lines = [f"■ {card.get('title', '')}", f"  {card.get('url', '')}"]
    if card.get("notice"):
        lines.append(f"  ({card['notice']})")
    lines += [f"  {card.get('summary_ko', '')}", f"  나한테는: {card.get('for_me', '')}", f"  이 카드인 이유: {card.get('why_this_card', '')}"]
    for label, key in (("장점", "pros"), ("단점", "cons")):
        for point in card.get(key) or []:
            evidence = point.get("evidence_url") or ""
            tail = f" ({evidence})" if evidence and evidence != card.get("url") else ""
            lines.append(f"  {label}: {point.get('text', '')}{tail}")
    if card.get("install_cmd") and card.get("type") in TOOL_TYPES:
        lines.append(f"  설치: {card['install_cmd']}")
    lines += [f"  {line}" for line in verify_lines(card)]
    if links and card.get("item_id"):
        lines += [f"  [{action}] {links(card, action)}" for action in actions_for(card)]
    lines.append(f"  trace_id {card.get('trace_id', '')}")
    return "\n".join(lines)


def _section(title: str) -> str:
    return (f'<h2 style="margin:26px 0 10px;padding:0 0 6px;border-bottom:1px solid {LINE};font-size:13px;font-weight:700;'
            f'letter-spacing:.04em;color:{MUTE}">{_e(title)}</h2>')


def _masthead(kicker: str, headline: str, sub: str) -> str:
    return (f'<div style="background:{MAST};border-radius:12px;padding:18px 20px;margin:0 0 6px">'
            f'<div style="font-size:11px;letter-spacing:.08em;color:{MAST_MUTE}">{_e(kicker)}</div>'
            f'<div style="margin:4px 0 0;font-size:22px;font-weight:700;color:{MAST_TEXT}">{_e(headline)}</div>'
            f'<div style="margin:4px 0 0;font-size:13px;color:{MAST_MUTE}">{_e(sub)}</div></div>')


def _page(inner: str) -> str:
    return (f'<div style="background:{PAPER};padding:16px 0"><div style="font-family:{FONT};max-width:640px;margin:0 auto;'
            f'padding:0 12px;color:{INK};line-height:1.55">{inner}'
            f'<p style="margin:20px 0 0;color:{MUTE};font-size:11px">요약은 원문을 바탕으로 AI가 썼습니다. '
            f'중요한 결정 전에는 원문 링크를 확인하세요.</p></div></div>')


def _day_label(day: date) -> str:
    return f"{day.month}월 {day.day}일 {WEEKDAYS[day.weekday()]}요일"


def render(day: date, role: str, cards: list[dict], empty_reason: str | None = None, links: Links | None = None) -> dict:
    """반환: {subject, html, text, body}. cards는 순위 순서의 card_json. body는 머리·꼬리 없이 칸과 카드만 (combine이 쓴다)."""
    news = [c for c in cards if c.get("type") not in TOOL_TYPES]
    tools = [c for c in cards if c.get("type") in TOOL_TYPES and not c.get("related")]
    related = [c for c in cards if c.get("related")]
    head = f"{day.year}년 {day.month}월 {day.day}일 · {role} 기준"
    if not cards:
        body_html = (f'<div style="background:#FFFFFF;border:1px solid {LINE};border-radius:10px;padding:18px;margin:12px 0">'
                     f'<h2 style="margin:0 0 6px;font-size:16px;color:{INK}">{EMPTY_TITLE}</h2>'
                     f'<p style="margin:0;color:{INK2};font-size:14px">{_e(empty_reason or "오늘 보여줄 항목이 없다")}</p></div>')
        body_text = f"{EMPTY_TITLE}\n{empty_reason or '오늘 보여줄 항목이 없다'}"
        sub = f"{role} 기준"
    else:
        body_html = (_section("뉴스") + ("".join(_card_html(c, links) for c in news)
                                         or f'<p style="color:{MUTE};font-size:14px">오늘 뉴스 카드 없음</p>')
                     + _section("새 MCP·스킬") + ("".join(_card_html(c, links) for c in tools)
                                                  or f'<p style="color:{MUTE};font-size:14px">{NO_TOOLS}</p>')
                     + (_section(RELATED_TITLE) + "".join(_card_html(c, links) for c in related) if related else ""))
        body_text = ("[뉴스]\n" + ("\n\n".join(_card_text(c, links) for c in news) or "오늘 뉴스 카드 없음")
                     + "\n\n[새 MCP·스킬]\n" + ("\n\n".join(_card_text(c, links) for c in tools) or NO_TOOLS)
                     + (f"\n\n[{RELATED_TITLE}]\n" + "\n\n".join(_card_text(c, links) for c in related) if related else ""))
        sub = f"{role} 기준 · 뉴스 {len(news)} · 도구 {len(tools) + len(related)}"
    page = _page(_masthead("TOOLSCOUT 아침 브리핑", _day_label(day), sub) + body_html)
    text = (f"toolscout 아침 브리핑\n{head}\n\n{body_text}\n\n"
            "요약은 원문을 바탕으로 AI가 썼습니다. 중요한 결정 전에는 원문 링크를 확인하세요.")
    return {"subject": subject(day, cards, empty_reason), "html": page, "text": text, "body": body_html}


def combine_subject(day: date, sections: list[dict]) -> str:
    when = f"{day.month}월 {day.day}일"
    cards = sum(s["cards"] for s in sections)
    return f"[개발 모드] {when} AI 브리핑 · 프로필 {len(sections)}개 · 카드 {cards}장"


def combine(day: date, sections: list[dict]) -> dict:
    """개발 모드 묶음 메일 (2026-09-16 사용자 결정: 프로필마다 한 통이 아니라 다 합쳐 한 통).

    sections: [{role, cards, html, text, body?}] (render 결과에 프로필 이름·카드 수를 더한 것, 발송함 순서)
    반환: {subject, html, text}. 맨 위에 프로필 목차, 아래에 프로필별 구역. 구역마다 머리를 되풀이하지 않도록 body를 쓴다.
    """
    heads = [f"프로필 {s['role']} · 카드 {s['cards']}장" for s in sections]
    toc = "".join(f'<div style="margin:2px 0;font-size:13px;color:{MAST_TEXT}">&middot; {_e(head)}</div>' for head in heads)
    body = "".join(f'<div style="margin:28px 0 0;padding:10px 14px;background:{INK};border-radius:8px;color:{MAST_TEXT};'
                   f'font-size:14px;font-weight:700">{_e(head)}</div>{section.get("body") or section["html"]}'
                   for head, section in zip(heads, sections))
    mast = (f'<div style="background:{MAST};border-radius:12px;padding:18px 20px;margin:0 0 6px">'
            f'<div style="font-size:11px;letter-spacing:.08em;color:{MAST_MUTE}">개발 모드 묶음 메일</div>'
            f'<div style="margin:4px 0 8px;font-size:22px;font-weight:700;color:{MAST_TEXT}">{_e(_day_label(day))}</div>'
            f'<div style="font-size:12px;color:{MAST_MUTE};margin:0 0 6px">가짜·테스트 프로필 {len(sections)}개의 브리핑을 한 통에 담았습니다.</div>'
            f'{toc}</div>')
    text = ("개발 모드 묶음 메일\n"
            f"가짜·테스트 프로필 {len(sections)}개의 브리핑을 한 통에 담았습니다.\n"
            + "\n".join(f"- {head}" for head in heads) + "\n\n"
            + "\n\n".join(f"{'=' * 40}\n{head}\n{'=' * 40}\n{section['text']}" for head, section in zip(heads, sections)))
    return {"subject": combine_subject(day, sections), "html": _page(mast + body), "text": text}
