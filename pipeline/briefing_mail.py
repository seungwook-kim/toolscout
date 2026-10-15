"""아침 브리핑 메일 본문 (계획안 부록 B 6 "이메일은 카드 전체", 예외 처리 표, 뼈대 완성 정의 "카드마다 trace_id").

2026-10-14 2차 리디자인(회의 3장): 표 레이아웃 600폭·인라인 스타일·color-scheme light·preheader.
- 순서: 머리(마크줄 → 날짜 → 기준·개수 → 이중 괘선) → 도구 줄 상자(새 MCP·스킬 1장 이상) → 업계 큰 소식 → 뉴스 → 새 MCP·스킬 → 관련(월요일) → 이번 주 요약(금요일, weekly.py) → 꼬리
- 카드는 웹과 같은 순서·낱말: 머리줄[꼭지 글 | 판정 배지] → 제목 → 메타 줄 → 요약 → 나에게 → 판정 → 고정 문구 → $ 설치 명령 → 좋은 점·아쉬운 점(각 2) → 버튼
- 2026-10-15 2라운드(회의 3장 2판): 세 무게(큰 소식 상자 없는 리드 28/22, 뉴스 BG 위 LINE 괘선 목록·좋은/아쉬운 점 뺌, 흰 상자는 도구만),
  머리 마크 타일칸+alt ">_"·설명 글·날짜 36/26, 도구 줄 머리는 verification.tool_head, 빈 날은 웹과 같은 세 줄 + "선별 기록 · {empty_reason}"
- 배지·판정 문장은 pipeline/verification.badge·verdict 하나만 쓴다. 시점("오늘·어제·n일 전")은 발송일(day) 기준이라 다시 만들어도 같다
- trace_id는 화면에 없다: 카드마다 HTML 주석, 텍스트 끝 "문의용 카드 번호", 메일 헤더 X-Toolscout-Trace(deliver.build_email)
- 외부 텍스트는 모두 HTML 이스케이프, 링크는 http(s)만. 그림은 마크·빈 날 PNG 두 장(https 절대 주소)뿐이고 꺼져도 다 읽힌다
- 색 상수 이름은 web/app.css 라이트 토큰과 1:1(tests/pipeline/check_mail_layout이 값을 비교). 메일은 CSS 변수를 못 쓴다
- mark: 받는 사람의 보이지 않는 워터마크(routes/watermark.py). 카드 본문 글과 AI 고지 문장 끝에 붙는다
"""
import html
import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlsplit

from pipeline import verification

TOOL_TYPES = ("mcp", "skill")
SAFE_URL = re.compile(r"^https?://[^\s\"'<>]+$")
NO_TOOLS = "오늘 새 도구 없음"
RELATED_TITLE = "이번 주 관련 MCP·스킬"  # 월요일 관련 카드(F3-b)
HEADLINE_LABEL = "오늘의 큰 소식"  # agent/headline.py 칸 이름. 2라운드부터 메일 꼭지에는 쓰지 않는다(칸 머리 '업계 큰 소식'이 말함)
EMPTY_TITLE = "오늘은 볼 만한 게 없었어요"  # 웹 index·cards.js와 같은 글(제목 subject도 이 상수)
EMPTY_BODY = "모은 소식과 도구를 살펴봤지만 내 기준에 맞는 게 없어 억지로 채우지 않았어요."
TAGLINE = "개발자용 AI·MCP 아침 브리핑"
MCP_SCOPE = "도구가 올바르게 동작하는지는 범위 밖입니다."  # 부록 D 5, 카드 템플릿 고정
SKILL_SCOPE = "안전 보증이 아니라 위험 신호 표시입니다."  # 부록 D 스킬 3, 카드 템플릿 고정
AI_NOTE = "요약은 원문을 바탕으로 AI가 썼습니다. 중요한 결정 전에는 원문 링크를 확인하세요."
JOINED = "toolscout에 가입해 매일 아침 브리핑을 받기로 해서 보내는 메일이에요."
STEP_KEYS = verification.STEPS
Links = Callable[[dict, str], str]
SITE = "https://toolscout-five.vercel.app"
IMG = f"{SITE}/static/img/mail/"

# 색·모서리: web/app.css 라이트 토큰과 같은 이름(--surface-2 → SURFACE_2)·같은 값
BG, SURFACE, SURFACE_2, LINE, LINE_CTL = "#F4F4F0", "#FFFFFF", "#EDEDE8", "#C4C6BF", "#7D8078"
INK, INK_2, MUTE, ON_INK, RULE, BRAND_TILE = "#16171A", "#43464D", "#62666E", "#FFFFFF", "#16171A", "#15181E"
BLAZE, BLAZE_INK, OK, OK_WASH = "#2E4CE6", "#1D35B8", "#1A6B3F", "#E6F3EC"
WARN, WARN_WASH, BAD, BAD_WASH = "#8F5200", "#FBF0DE", "#B3261E", "#FCEBE9"
R_CTL, R_CARD = "8px", "10px"
FONT = "'Pretendard Variable',Pretendard,-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕','Noto Sans KR','Segoe UI',Roboto,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Courier New',monospace"
WEEKDAYS = "월화수목금토일"
KST = timezone(timedelta(hours=9))
RP = 'role="presentation" cellpadding="0" cellspacing="0" border="0"'
DIST = ((r"^https?://", "원격 전용"), (r"^(npx|npm|pnpm|bunx)\b", "npm"), (r"^(uvx|pip|pipx|uv)\b", "PyPI"), (r"^docker\b", "Docker"))
SYM = {"ok": "&#10003; ", "shield": "&#10003; ", "na": "&#9675; ", "bad": "&#10005; "}
TXT_SYM = {"ok": "✓ ", "shield": "✓ ", "na": "○ ", "bad": "✕ "}
GAP = '<td width="8" style="width:8px;font-size:0;line-height:0">&nbsp;</td>'
CAP = f"font-size:13px;line-height:20px;color:{MUTE}"
BTN = f"display:inline-block;font-size:14px;line-height:20px;text-decoration:none;white-space:nowrap"


def actions_for(card: dict) -> list[str]:
    if card.get("type") in TOOL_TYPES:
        return ["써봤음", "관심없음", "이상함"]
    return ["이상함"] if card.get("headline") else ["관심없음", "이상함"]


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


def verify_lines(card: dict) -> list[str]:
    """예전 한 줄 검증 문장(tests/verify/check_mcp_now가 쓴다). 메일 화면은 verification.verdict를 쓴다."""
    if card.get("type") == "mcp":
        verification_ = card.get("verification") or {}
        steps = " / ".join((verification_.get(k) or {}).get("label", "") for k in STEP_KEYS if verification_.get(k))
        return [f"직접 깔아봤더니: {steps}" if steps else f"직접 깔아봤더니: {card.get('verification_note') or '검증 예정'}", MCP_SCOPE]
    if card.get("type") == "skill":
        risk = card.get("risk_signal") or {}
        if not risk:
            return [f"SKILL.md 읽어봤더니: {card.get('verification_note') or '판독 예정'}", SKILL_SCOPE]
        basis = f" ({risk['basis']})" if risk.get("basis") else ""
        quote = f" \"{risk['quote']}\"" if risk.get("quote") else ""
        return [f"SKILL.md 읽어봤더니: 위험 신호 {risk.get('label', '')}{basis}{quote}", SKILL_SCOPE]
    return []


def _cut(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    head = text[:n]
    return (head[:head.rfind(" ")] if head.rfind(" ") > n // 2 else head).rstrip(" ,.·") + "…"


def _num(value) -> str:
    """숫자 하나를 고정폭 span으로. 앞뒤 공백은 부르는 쪽 글에 두지 않는다("5 개"처럼 띄지 않게)."""
    return f'<span style="font-family:{MONO}">{value}</span>'


def _mono(escaped: str) -> str:
    """숫자와 키 이름(NOTES_API_KEY)만 고정폭. 이미 이스케이프한 글에 쓰고 &#...; 같은 엔티티는 건드리지 않는다."""
    return re.sub(r"(&#?\w+;)|(\d[\d:.-]*|[A-Z][A-Z0-9_]{2,})",
                  lambda m: m[1] or f'<span style="font-family:{MONO}">{m[2]}</span>', escaped)


def _ago(card: dict, day: date | None) -> str:
    """발송일 기준 날짜 차이(지금 시각을 쓰지 않아 미리보기·재발송 때 같은 글)."""
    raw = (card.get("item_meta") or {}).get("published_at")
    try:
        at = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw and day else None
    except ValueError:
        at = None
    if not at:
        return ""
    days = (day - (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).astimezone(KST).date()).days
    return "오늘" if days <= 0 else "어제" if days == 1 else f"{days}일 전"


def tool_name(title: str) -> tuple[str, str]:
    """웹 Cards.toolName과 같은 규칙: "com.apify/apify-mcp-server 0.15.7" → (이름, 버전)."""
    m = re.match(r"^(.*?)(?:\s+v?(\d+(?:\.\d+)+[\w.-]*))?$", str(title or ""), re.S)
    ns = re.match(r"^([a-z0-9-]+(?:\.[a-z0-9-]+)+)/(.+)$", m[1], re.I)
    return (ns[2] if ns else m[1]), (m[2] or "")


def _kind(card: dict) -> str:
    """꼭지 글. 뉴스는 주제 이름, 도구는 웹 Cards.kind와 같은 "MCP · 커뮤니티" 꼴."""
    if card.get("type") not in TOOL_TYPES:
        return card.get("topic_label") or "뉴스"
    github = (card.get("item_meta") or {}).get("source") == "github_search"
    if card["type"] == "skill":
        return "스킬 · " + ("공식" if re.search(r"github\.com/anthropics/", card.get("url") or "") else "GitHub" if github else "커뮤니티")
    ns = re.match(r"^([a-z0-9-]+(?:\.[a-z0-9-]+)+)/", str(card.get("title") or ""), re.I)
    source = "GitHub" if github else "" if not ns else "커뮤니티" if ns[1].startswith("io.github.") else "공식"
    return f"MCP · {source}" if source else "MCP"


def _meta(card: dict, day: date | None) -> list[tuple[str, str]]:
    """메타 줄 [(html, text)]. 뉴스: 출처 도메인 · 시점 / 도구: 배포처 · ☆ 별 수 · n일 전 등록 · 주제. 별은 웹 외곽선 별과 같은 ☆."""
    ago = _ago(card, day)
    if card.get("type") not in TOOL_TYPES:
        return [(_e(x), x) for x in (_host(card.get("url")), ago) if x]
    stars = (card.get("item_meta") or {}).get("stars")
    stars = f"{int(stars):,}" if isinstance(stars, (int, float)) else ""
    dist = next((name for pattern, name in DIST if re.match(pattern, card.get("install_cmd") or "")), "")
    parts = [(_e(dist), dist) if dist else None, (f"&#9734; {_num(stars)}", f"별 {stars}") if stars else None,
             (f"{ago} 등록", f"{ago} 등록") if ago else None, (_e(card["topic_label"]), card["topic_label"]) if card.get("topic_label") else None]
    return [p for p in parts if p]


def _badge_html(b: dict | None) -> str:
    """카드 머리줄·도구 줄 끝 배지. 문제(bad·warn)만 채운 칩, 나머지는 글자."""
    if not b:
        return ""
    word, problem = _e(b["word"]), b["tone"] in ("bad", "warn")
    fg, wash = (BAD, BAD_WASH) if b["tone"] == "bad" else (WARN, WARN_WASH) if b["tone"] == "warn" else (OK if b["tone"] == "pass" else INK_2, "")
    if problem:
        return (f'<table {RP} align="right"><tr><td style="background-color:{wash};border-radius:{R_CTL};padding:2px 8px;font-size:13px;'
                f'line-height:20px;font-weight:700;color:{fg};white-space:nowrap">{word}</td></tr></table>')
    return f'<span style="font-size:13px;line-height:20px;font-weight:700;color:{fg}">{SYM.get(b["icon"], "")}{word}</span>'


def _p(inner: str, top: int = 12, style: str = f"font-size:14px;line-height:22px;color:{INK_2}") -> str:
    return f'<p style="margin:{top}px 0 0;{style}">{inner}</p>'


def _code(cmd: str, lead: str = "$") -> str:
    """$(또는 "원격 주소")는 따로 칸: 명령 칸만 전체 선택되어 복사할 때 $가 딸려 가지 않는다."""
    lead_font = f"font-family:{MONO};" if lead == "$" else "white-space:nowrap;"
    return (f'<table {RP} width="100%"><tr><td valign="top" class="ts-code" style="{"width:22px;" if lead == "$" else ""}background-color:{SURFACE_2};border-radius:6px 0 0 6px;'
            f'padding:10px 0 10px 12px;{lead_font}{CAP}">{lead}</td><td valign="top" class="ts-code" style="background-color:{SURFACE_2};'
            f'border-radius:0 6px 6px 0;padding:10px 12px 10px 6px;font-family:{MONO};font-size:13px;line-height:20px;color:{INK};'
            f'word-break:break-all;-webkit-user-select:all;user-select:all">{_e(cmd)}</td></tr></table>')


def _verdict_html(card: dict) -> tuple[int, str]:
    """(위 띄움 px, html). 카드 아래쪽 표의 한 행에 들어간다."""
    v = verification.verdict(card)
    if not v:
        return 0, ""
    mcp = card.get("type") == "mcp"
    at = f'{"샌드박스 확인" if mcp else "검토"} <span style="font-family:{MONO}">{_e(v["at"])}</span> · ' if v.get("at") else ""
    caption = _p(at + (MCP_SCOPE if mcp else SKILL_SCOPE), 2 if v["mode"] in ("line", "none") else 6, CAP)
    if v["mode"] == "line":
        return 0, _p(f'<b style="color:{OK}">&#10003; {_e(v["head"])}</b>' + "".join(f" · {_mono(_e(r))}" for r in v["rest"])) + caption
    if v["mode"] == "none":
        return 0, _p(f'<b>&#9675; {_e(v["head"])}</b>' + (f'{v["sep"]}{_e(v["note"])}' if v.get("note") else "")) + caption
    if v["mode"] == "skill":
        quote = (f'<table {RP} width="100%"><tr><td style="padding-top:6px"><table {RP} width="100%"><tr><td class="ts-code" style="background-color:'
                 f'{SURFACE_2};border-radius:6px;padding:8px 12px;font-family:{MONO};font-size:13px;line-height:20px;color:{INK};word-break:break-all">'
                 f'{_e(v["quote"])}</td></tr></table></td></tr></table>') if v["quote"] else ""
        return 0, _p(_e(v["head"])) + quote + caption

    def cell(name: str, word: str, cls: str) -> str:
        fill = {"bad": BAD_WASH, "key": SURFACE_2}.get(cls)
        box = f"background-color:{fill};border:1px solid {fill}" if fill else f"border:1px solid {LINE}"
        return (f'<td width="50%" style="width:50%;{box};border-radius:6px;padding:8px 10px;font-size:14px;line-height:20px">'
                f'<span style="font-size:13px;color:{INK_2 if fill else MUTE}">{name}</span>&nbsp; '
                f'<b style="color:{ {"ok": OK, "bad": BAD, "key": INK}.get(cls, INK_2)}">{SYM.get(cls, "")}{_e(word)}</b></td>')
    c = [cell(*x) for x in v["cells"]]
    return 12, (f'<table {RP} width="100%"><tr>{c[0]}{GAP}{c[1]}</tr><tr><td colspan="3" height="6" style="height:6px;font-size:0;line-height:0">'
                f'&nbsp;</td></tr><tr>{c[2]}{GAP}{c[3]}</tr></table>{caption}')


def _verdict_text(card: dict) -> list[str]:
    v = verification.verdict(card)
    if not v:
        return []
    mcp = card.get("type") == "mcp"
    at = f'{"샌드박스 확인" if mcp else "검토"} {v["at"]} · ' if v.get("at") else ""
    head = {"line": lambda: " · ".join([f"✓ {v['head']}", *v["rest"]]),
            "none": lambda: f"○ {v['head']}" + (f"{v['sep']}{v['note']}" if v.get("note") else ""),
            "skill": lambda: v["head"] + (f' "{v["quote"]}"' if v["quote"] else ""),
            "grid": lambda: " · ".join(f"{n} {TXT_SYM.get(c, '')}{w}" for n, w, c in v["cells"])}[v["mode"]]()
    return [head if v["mode"] == "skill" else f"판정: {head}", at + (MCP_SCOPE if mcp else SKILL_SCOPE)]


def _points(card: dict, link: str | None) -> list[tuple[str, str, list[tuple[str, str]]]]:
    """좋은 점·아쉬운 점 각 2개까지 [(라벨, 색, [(글, 근거 링크)])]. 근거 링크는 원문과 다를 때만. 빈 묶음은 뺀다."""
    out = []
    for label, key, color in (("좋은 점", "pros", OK), ("아쉬운 점", "cons", WARN)):
        items = [(p["text"], ev if (ev := _url(p.get("evidence_url"))) and ev != link else "") for p in card.get(key) or [] if p.get("text")][:2]
        if items:
            out.append((label, color, items))
    return out


def _buttons(card: dict, links: Links, hint: bool) -> str:
    cells = GAP.join(f'<td style="border:1px solid {LINE_CTL};border-radius:{R_CTL};mso-padding-alt:11px 14px"><a href="{_e(links(card, a))}" '
                     f'style="{BTN};padding:11px 14px;font-weight:500;color:{INK_2}">{a}</a></td>' for a in actions_for(card))
    tip = f'<tr><td style="padding-top:8px;{CAP}">누르면 내일 추천에 반영돼요. 이상함은 이유도 고를 수 있어요.</td></tr>' if hint else ""
    return (f'<table {RP} width="100%"><tr><td style="border-top:1px solid {LINE};padding-top:12px"><table {RP}><tr>{cells}</tr></table></td></tr>'
            f'{tip}</table>')


def box(inner: str, frame: str = "", outer: str = "0 20px 12px", pad: str = "20px") -> str:
    """흰 카드 한 장(바깥 tr). frame이 없으면 1px 테두리."""
    frame = frame or f"border:1px solid {LINE};border-radius:{R_CARD}"
    return (f'<tr><td class="ts-pad" style="padding:{outer}"><table {RP} width="100%" style="background-color:{SURFACE};{frame}">'
            f'<tr><td class="ts-card" style="padding:{pad};font-family:{FONT}">{inner}</td></tr></table></td></tr>')


def section(title: str, count: int | None = None, note: str = "") -> str:
    """칸 머리(조간): 위 2px 괘선 + 굵은 이름 + 개수 + 짧은 보조 글."""
    num = f' <span style="font-family:{MONO};font-size:15px;font-weight:400;color:{MUTE}">{count}</span>' if count is not None else ""
    sub = f'<span style="font-size:13px;font-weight:400;letter-spacing:0;color:{MUTE}">&nbsp; {_e(note)}</span>' if note else ""
    return (f'<tr><td class="ts-pad" style="padding:28px 20px 12px"><table {RP} width="100%"><tr><td style="border-top:2px solid {RULE};'
            f'padding-top:8px;font-family:{FONT};font-size:17px;line-height:23px;font-weight:800;letter-spacing:-0.02em;color:{INK}">'
            f'{_e(title)}{num}{sub}</td></tr></table></td></tr>')


def _card_html(card: dict, links: Links | None = None, day: date | None = None, hint: bool = False, first: bool = True) -> str:
    """세 무게(2라운드): 큰 소식은 상자 없는 리드(첫 장 28px, 둘째부터 1px 괘선 + 22px), 뉴스는 BG 위 괘선 목록(좋은 점·아쉬운 점 없음),
    흰 상자는 도구만. first는 그 칸의 첫 장(괘선 없음, 칸 머리가 대신함)."""
    tool, link, hl = card.get("type") in TOOL_TYPES, _url(card.get("url")), bool(card.get("headline"))
    kind = _kind(card)  # 큰 소식도 주제만(웹과 같음)
    badge = _badge_html(verification.badge(card))
    head = (f'<table {RP} width="100%"><tr><td valign="middle" style="font-size:13px;line-height:20px;font-weight:700;color:{INK_2}">{_e(kind)}</td>'
            + (f'<td align="right" valign="middle" style="white-space:nowrap;padding-left:8px">{badge}</td>' if badge else "") + "</tr></table>")
    name, version = tool_name(card.get("title")) if tool else (card.get("title"), "")
    version = (version or (card.get("item_meta") or {}).get("version") or "").lstrip("vV") if tool else ""
    title = _e(name) + f'<span style="color:{MUTE};font-weight:400">&nbsp;&#8599;&#xFE0E;</span>' if link else _e(name)
    title = f'<a href="{_e(link)}" style="color:{INK};text-decoration:none">{title}</a>' if link else title
    ver = f'<span style="font-family:{MONO};font-size:13px;font-weight:400;color:{MUTE}">&nbsp;v{_e(version)}</span>' if version else ""
    lead = hl and first
    cls, size = (' class="ts-lead"', "28px;line-height:35px;font-weight:800;letter-spacing:-0.03em") if lead else (
        ' class="ts-hl"', "22px;line-height:28px;font-weight:700") if hl else ("", "17px;line-height:25px;font-weight:700")
    parts = [head, f'<h3{cls} style="margin:8px 0 0;font-size:{size};color:{INK}">{title}{ver}</h3>']
    if meta := _meta(card, day):
        parts.append(_p(" · ".join(h for h, _ in meta), 4, CAP))
    # 요약 아래 블록은 표 하나의 행으로 잇는다(블록마다 바깥 표를 두면 8장에서 수 KB가 늘어 60KB를 넘기 쉽다)
    summary = "16px;line-height:26px" if lead else "15px;line-height:24px"
    parts.append(f'<p style="margin:10px 0 12px;font-size:{summary};color:{INK_2}">{_e(card.get("summary_ko"))}</p>')
    rows = [(f"border-top:1px dotted {LINE_CTL};padding-top:10px;font-size:15px;line-height:23px;font-weight:500;color:{INK}",
             f'<b style="font-size:13px;font-weight:700;color:{BLAZE}">나에게</b>&nbsp; {_e(card.get("for_me"))}')]
    if tool:
        rows.append(_verdict_html(card))
        if cmd := card.get("install_cmd"):
            rows.append((12, _code(cmd, "원격 주소" if re.match(r"^https?://", cmd) else "$")))
    if (tool or hl) and (points := _points(card, link)):  # 뉴스는 뺌(웹은 자세히에 있음). 묶음마다 한 줄(항목은 줄바꿈)
        ev_link = lambda ev: f' <a href="{_e(ev)}" style="color:{MUTE};font-size:13px">근거</a>' if ev else ""  # noqa: E731
        rows.append((12, f'<table {RP} width="100%">' + "".join(
            f'<tr><td width="68" valign="top" style="width:68px;padding:2px 0;font-size:13px;line-height:21px;font-weight:700;color:{color};'
            f'white-space:nowrap">{label}</td><td valign="top" style="padding:2px 0;font-size:14px;line-height:21px;color:{INK_2}">'
            + "<br>".join(_e(text) + ev_link(ev) for text, ev in items) + "</td></tr>" for label, color, items in points) + "</table>"))
    if links and card.get("item_id"):
        rows.append((16, _buttons(card, links, hint)))
    parts.append(f'<table {RP} width="100%">' + "".join(f'<tr><td style="{pad if isinstance(pad, str) else f"padding-top:{pad}px"}">{inner}</td></tr>'
                                                        for pad, inner in rows if inner) + "</table>")
    trace = re.sub(r"-{2,}", "-", re.sub(r"[^0-9A-Za-z_.:-]", "", str(card.get("trace_id") or "")))
    inner = f"<!-- trace_id {trace} -->" + "".join(parts)
    if tool:
        return box(inner)
    if lead:
        return f'<tr><td class="ts-pad" style="padding:4px 20px 24px;font-family:{FONT}">{inner}</td></tr>'
    rule = "" if first else f"border-top:1px solid {LINE};"
    pad = "0 20px 24px" if hl else "0 20px"
    return (f'<tr><td class="ts-pad" style="padding:{pad}"><table {RP} width="100%"><tr><td style="{rule}padding:{"20px 0 0" if hl else "18px 0"};'
            f'font-family:{FONT}">{inner}</td></tr></table></td></tr>')


def _card_text(card: dict, links: Links | None = None, day: date | None = None, n: int | None = None) -> str:
    tool, b = card.get("type") in TOOL_TYPES, verification.badge(card)
    meta = " · ".join(t for _, t in _meta(card, day))
    kind = _kind(card)  # 큰 소식 앞말은 칸 머리 "== 업계 큰 소식 =="가 말한다
    tail = f"  [{b['word']}]" if b else ""
    first = f"{n}. " if n else ""
    lines = ([f"{first}{card.get('title', '')} ({' · '.join(x for x in (kind, meta) if x)}){tail}"] if tool
             else [f"{first}{card.get('title', '')}", f"   {' · '.join(x for x in (kind, meta) if x)}{tail}"])
    lines += [f"   <{card.get('url', '')}>", f"   {card.get('summary_ko', '')}", f"   나에게: {card.get('for_me', '')}"]
    if tool:
        lines += [f"   {x}" for x in _verdict_text(card)]
        if card.get("install_cmd"):
            lines.append(f"   {'원격 주소:' if re.match(r'^https?://', card['install_cmd']) else '$'} {card['install_cmd']}")
    if tool or card.get("headline"):  # 뉴스는 좋은 점·아쉬운 점을 뺀다(HTML과 같게)
        lines += [f"   {label}: {text}" + (f" <{ev}>" if ev else "") for label, _, items in _points(card, _url(card.get("url"))) for text, ev in items]
    if links and card.get("item_id"):
        lines += [f"   [{action}] <{links(card, action)}>" for action in actions_for(card)]
    return "\n".join(lines)


def _day_label(day: date) -> str:
    return f"{day.month}월 {day.day}일 {WEEKDAYS[day.weekday()]}요일"


def _mast(day: date, line: str) -> str:
    """line은 이미 만든 html(직군은 이스케이프, 숫자는 _num). 마크는 타일색 칸에 넣어 이미지가 꺼지면 흰 '>_'가 보인다."""
    rule = lambda h, top: f'<tr><td height="{h}" style="height:{h}px;{top}font-size:0;line-height:0;mso-line-height-rule:exactly">&nbsp;</td></tr>'  # noqa: E731
    return (f'<tr><td class="ts-pad" style="padding:0 20px 20px;font-family:{FONT}"><table {RP} width="100%"><tr>'
            # 타일색은 안쪽 28x28 칸에만(320폭에서 설명 글이 접혀 줄이 높아져도 타일이 늘지 않게)
            f'<td width="28" valign="middle" style="width:28px"><table {RP}><tr><td width="28" height="28" bgcolor="{BRAND_TILE}" '
            f'style="width:28px;height:28px;background-color:{BRAND_TILE};border-radius:6px"><img src="{IMG}mark-56.png" width="28" height="28" alt="&gt;_" '
            f'style="display:block;width:28px;height:28px;border:0;border-radius:6px;font-family:{MONO};font-size:13px;line-height:28px;font-weight:700;'
            f'color:{ON_INK};text-align:center"></td></tr></table></td>'
            f'<td valign="middle" style="padding-left:8px;font-size:16px;line-height:20px;font-weight:800;letter-spacing:-0.04em;color:{INK}">toolscout '
            f'<span style="font-size:13px;font-weight:400;letter-spacing:0;color:{MUTE}">&nbsp;{TAGLINE}</span></td><td align="right" valign="middle" '
            f'style="font-size:13px;line-height:20px;white-space:nowrap"><a href="{SITE}/" style="color:{BLAZE_INK};text-decoration:underline">웹에서 보기</a></td></tr></table>'
            f'<h1 class="ts-h1" style="margin:16px 0 0;font-family:{FONT};font-size:36px;line-height:42px;font-weight:800;letter-spacing:-0.03em;'
            f'color:{INK}">{_day_label(day)}</h1>{_p(line, 6, f"font-size:14px;line-height:21px;color:{INK_2}")}'
            f'<table {RP} width="100%"><tr><td style="padding-top:16px"><table {RP} width="100%">{rule(2, f"border-top:2px solid {RULE};")}'
            f'{rule(2, "")}{rule(1, f"border-top:1px solid {RULE};")}</table></td></tr></table></td></tr>')


def _tool_rows(cards: list[dict], tools: list[dict]) -> str:
    """'오늘 한눈에' 자리의 도구 줄 상자(웹 레일 맨 위 칸·폰 띠와 한 부품). 머리는 verification.tool_head 글 그대로(숫자만 고정폭),
    줄은 이름(원문 링크)+버전 | 카드 머리줄과 같은 배지. 줄 40px, 줄 사이 1px LINE. $ 명령은 넣지 않는다(도구 카드에 있다)."""
    def row(c: dict) -> str:
        name, version = tool_name(c.get("title"))
        version = (version or (c.get("item_meta") or {}).get("version") or "").lstrip("vV")
        name = f'<a href="{_e(link)}" style="color:{INK};text-decoration:none">{_e(name)}</a>' if (link := _url(c.get("url"))) else _e(name)
        ver = f'<span style="font-family:{MONO};font-size:13px;font-weight:400;color:{MUTE}">&nbsp;v{_e(version)}</span>' if version else ""
        badge = _badge_html(verification.badge(c))
        return (f'<tr><td valign="middle" style="border-top:1px solid {LINE};padding:10px 0;font-size:15px;line-height:20px;font-weight:600;color:{INK}">'
                f'{name}{ver}</td><td align="right" valign="middle" style="border-top:1px solid {LINE};padding:10px 0 10px 8px;white-space:nowrap">{badge}</td></tr>')
    head = verification.tool_head(cards, _num)
    return box(f'<p style="margin:0 0 10px;font-size:14px;line-height:20px;font-weight:700;color:{INK}">{head}</p>'
               f'<table {RP} width="100%">{"".join(row(c) for c in tools)}</table>', outer="0 20px 8px", pad="14px 16px 4px")


def _empty(reason: str | None) -> str:
    """빈 날(웹과 같은 세 줄): 제목 · 본문 · 13px '선별 기록 · {empty_reason}'. 그림은 타일색 칸에 넣어 이미지가 꺼지면 같은 색 칸만 남는다."""
    a = f"{BTN};font-weight:700;color:{ON_INK};padding:12px 18px"
    record = _p(f"선별 기록 · {_e(reason)}", 6, CAP) if reason else ""
    return box(f'<table {RP}><tr><td width="96" bgcolor="{BRAND_TILE}" style="width:96px;background-color:{BRAND_TILE};border-radius:{R_CARD}">'
               f'<img src="{IMG}empty-192.png" width="96" height="72" alt="" style="display:block;width:96px;height:72px;border:0;border-radius:{R_CARD}">'
               f'</td></tr></table><h2 style="margin:16px 0 0;font-family:{FONT};font-size:19px;line-height:27px;font-weight:700;color:{INK}">{EMPTY_TITLE}</h2>'
               + _p(EMPTY_BODY, 8, f"font-size:15px;line-height:24px;color:{INK_2}") + record
               # 버튼 둘은 왼쪽으로 띄운 표 두 개라 좁은 폭(320)에서는 다음 줄로 접힌다. 넓히기가 빈 날의 다음 행동이라 앞(채움)
               + f'<table {RP} width="100%"><tr><td style="padding-top:8px"><table {RP} align="left"><tr><td style="padding:8px 8px 0 0">'
               f'<table {RP}><tr><td bgcolor="{INK}" style="background-color:{INK};border-radius:{R_CTL};mso-padding-alt:12px 18px"><a href="{SITE}/settings#topics" '
               f'style="{a}">관심 주제 넓히기</a></td></tr></table></td></tr></table><table {RP} align="left"><tr><td style="padding:8px 0 0">'
               f'<table {RP}><tr><td style="border:1px solid {LINE_CTL};border-radius:{R_CTL};mso-padding-alt:11px 16px"><a href="{SITE}/history" '
               f'style="{BTN};font-weight:500;color:{INK_2};padding:11px 16px">지난 브리핑 보기</a></td></tr></table></td></tr></table></td></tr></table>',
               outer="8px 20px 12px", pad="24px 20px")


def _foot(mark: str) -> str:
    a = f'style="color:{MUTE};text-decoration:underline"'
    return (f'<tr><td class="ts-pad" style="padding:24px 20px 0;font-family:{FONT};{CAP}"><p style="margin:0">{AI_NOTE}{mark}</p>'
            f'<p style="margin:8px 0 0">{JOINED}</p><p style="margin:8px 0 0"><a href="{SITE}/" {a}>웹에서 보기</a> · '
            f'<a href="{SITE}/?ask=1" {a}>AI에게 질문하기</a> · <a href="{SITE}/settings" {a}>기준 바꾸기</a></p>'
            f'<p style="margin:8px 0 0">&copy; 2026 toolscout · {TAGLINE}</p></td></tr>')


HEAD = ('<!doctype html><html lang="ko" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:o="urn:schemas-microsoft-com:office:office"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="X-UA-Compatible" content="IE=edge"><meta name="x-apple-disable-message-reformatting">'
        '<meta name="format-detection" content="telephone=no,date=no,address=no,email=no,url=no"><meta name="color-scheme" content="light">'
        '<meta name="supported-color-schemes" content="light"><title>__TITLE__</title><!--[if mso]><noscript><xml><o:OfficeDocumentSettings>'
        '<o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><style>body,table,td,p,a,span,b,h1,h2,h3'
        "{font-family:'Malgun Gothic',Arial,sans-serif !important}.ts-code,.ts-code *{font-family:Consolas,'Courier New',monospace !important}"
        '</style><![endif]--><style>:root{color-scheme:light;supported-color-schemes:light}body{margin:0!important;padding:0!important;'
        'width:100%!important;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}table,td{border-collapse:collapse;mso-table-lspace:0pt;'
        'mso-table-rspace:0pt}img{border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic}a[x-apple-data-detectors]'
        '{color:inherit!important;text-decoration:none!important}@media (max-width:620px){.ts-pad{padding-left:12px!important;'
        'padding-right:12px!important}.ts-card{padding:16px!important}.ts-h1{font-size:26px!important;line-height:32px!important}'
        '.ts-lead{font-size:22px!important;line-height:28px!important}.ts-hl{font-size:19px!important;line-height:26px!important}}</style></head>')


def _preheader(cards: list[dict], heads: list, news: list, tools: list, weekly: bool) -> str:
    if not cards:
        return "오늘은 기준에 맞는 소식이 없어 카드를 만들지 않았어요."
    clean = lambda c: _cut(re.sub(r"\[[^\]]*\]\s*", "", str(c.get("title") or "")).strip(), 30)  # noqa: E731
    text = f"{clean(heads[0])} 외 뉴스 {len(news)} · 새 도구 {len(tools)}" if heads else clean(cards[0]) + (f" 외 {len(cards) - 1}장" if len(cards) > 1 else "")
    mcps = [c for c in cards if c.get("type") == "mcp"]
    if passed := sum((verification.badge(c) or {}).get("word") == "검증 통과" for c in mcps):
        text += f" (검증 통과 {passed}/{len(mcps)})"
    return text + (" · 이번 주 요약 포함" if weekly else "")


def render(day: date, role: str, cards: list[dict], empty_reason: str | None = None, links: Links | None = None,
           weekly: dict | None = None, mark: str = "") -> dict:
    """반환: {subject, html, text, body}. cards는 순위 순서의 card_json(웹과 같은 topic_label·item_meta가 붙어 있으면 메타 줄에 쓴다).
    body는 머리·꼬리 없이 칸과 카드만. weekly: 금요일 "이번 주 요약" {html, text} (pipeline/weekly.py), 꼬리 바로 위에 붙인다.
    mark: 받는 사람의 보이지 않는 워터마크. 저장된 카드 원문은 바꾸지 않는다(복사본에만)."""
    if mark:
        from routes import watermark  # 메일 만들 때만 쓴다(순환 import 방지)

        cards = watermark.mark_cards(cards, mark)
    heads = [c for c in cards if c.get("type") not in TOOL_TYPES and c.get("headline")]
    news = [c for c in cards if c.get("type") not in TOOL_TYPES and not c.get("headline")]
    tools = [c for c in cards if c.get("type") in TOOL_TYPES and not c.get("related")]
    related = [c for c in cards if c.get("type") in TOOL_TYPES and c.get("related")]
    order = heads + news + tools + related
    number = {id(c): n for n, c in enumerate(order, 1)}  # 텍스트 카드 번호 = 한눈에 목록 번호
    who = f"{role or '직군 미설정'} 기준"
    counts = " · ".join(x for x in (f"큰 소식 {len(heads)}" if heads else "", f"뉴스 {len(news)}", f"도구 {len(tools) + len(related)}") if x)
    today_line = f"오늘 {len(cards)}장: {counts}" if cards else "오늘 카드 없음"
    # 머리 둘째 줄(html): 구역 개수는 칸 머리 숫자와 겹쳐 뺀다(웹 마스트헤드와 같음). 금요일이면 끝에 요약 자리 안내
    friday = " · 이번 주 요약은 맨 아래" if weekly else ""
    mast_line = f"{_e(who)} · " + (f"오늘 {_num(len(cards))}장" if cards else "오늘 카드 없음") + friday
    hint = next((id(c) for c in order if links and c.get("item_id")), None)
    rows, text = [], []
    if not cards:
        rows.append(_empty(empty_reason))
        record = f"\n선별 기록 · {empty_reason}" if empty_reason else ""
        text.append(f"{EMPTY_TITLE}\n{EMPTY_BODY}{record}\n지난 브리핑 보기: <{SITE}/history>")
    else:
        label = lambda c: "큰 소식" if c.get("headline") and c.get("type") not in TOOL_TYPES else {"mcp": "MCP", "skill": "스킬"}.get(c.get("type"), "뉴스")  # noqa: E731
        if tools:  # '오늘 한눈에' 상자 → 도구 줄 상자(새 MCP·스킬 1장 이상)
            rows.append(_tool_rows(cards, tools))
        if len(cards) >= 4:  # 텍스트는 번호로 카드를 찾으니 번호 목록 유지
            text.append("오늘 한눈에\n" + "\n".join(f"{n}. [{label(c)}] {c.get('title', '')}" + (f" ({b['word']})" if (b := verification.badge(c)) else "")
                                                for n, c in enumerate(order, 1)))
        blocks = ([("업계 큰 소식", None, "모두에게 같은 소식", heads, "")] if heads else []) + [
            ("뉴스", len(news), "", news, "오늘 뉴스 카드 없음"), ("새 MCP·스킬", len(tools), "7일 안 새로 등록", tools, NO_TOOLS)] + (
            [(RELATED_TITLE, None, "", related, "")] if related else [])
        for title, count, note, group, none in blocks:
            rows.append(section(title, count, note) + ("".join(_card_html(c, links, day, id(c) == hint, n == 0) for n, c in enumerate(group))
                                                       or f'<tr><td class="ts-pad" style="padding:0 20px 12px;font-size:14px;line-height:21px;color:{MUTE}">{none}</td></tr>'))
            text.append(f"== {title} ==\n\n" + ("\n\n".join(_card_text(c, links, day, number[id(c)]) for c in group) or none))
    if weekly:
        rows.append(weekly["html"])
        text.append(weekly["text"])
    body = "".join(rows)
    preheader = _e(_preheader(order, heads, news, tools, bool(weekly))) + "&#847;&zwnj;&nbsp;" * 60  # 제목은 바깥 글이라 이스케이프
    page = (HEAD.replace("__TITLE__", f"{day.month}월 {day.day}일 AI 브리핑") + f'<body style="margin:0;padding:0;background-color:{BG}">'
            f'<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all">{preheader}</div>'
            f'<table {RP} width="100%" style="background-color:{BG}"><tr><td align="center" style="padding:24px 0 32px">'
            f'<!--[if mso]><table {RP} align="center" width="600"><tr><td><![endif]--><table {RP} width="100%" style="width:100%;max-width:600px">'
            f'{_mast(day, mast_line)}{body}{_foot(mark)}</table><!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>')
    traces = ", ".join(str(c.get("trace_id")) for c in order if c.get("trace_id"))
    text = (f"toolscout 아침 브리핑\n{_day_label(day)} · {who}\n{today_line}{friday}\n웹에서 보기: <{SITE}/>\n\n" + f"\n\n{'-' * 40}\n".join(text)
            + f"\n\n{'-' * 40}\n{JOINED}\n기준 바꾸기: <{SITE}/settings>\nAI에게 질문하기: <{SITE}/?ask=1>\n"
            + (f"문의용 카드 번호: {traces}\n" if traces else "") + f"{AI_NOTE}{mark}")
    return {"subject": subject(day, cards, empty_reason), "html": page, "text": text, "body": body}
