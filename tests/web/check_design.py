"""화면 검수: run_stats·item_meta 읽기 API(A) + 화면 파일 정적 검사(B) + PWA manifest·아이콘(C).

A는 이미 구현된 pipeline/persist.py·routes/briefings.py·db.py 규격을 검수한다(모델 호출 없음).
B는 app.css 토큰(라이트·다크, 자동 다크 == 수동 다크, 대비 기준 계산: line/bg·line/surface 1.5, --fs-4xl, --hl-border 없음)·공통 컴포넌트, 색은 토큰만 쓰는지(app·cards·profile.css와 모든 HTML <style>),
화면 파일 공통 요소(head 링크·파비콘), SVG 안전·크기 예산·dawn 그림, 판정·도구 머리 사례 파일, 금지 사항(web/ 전체)을 본다. C는 PWA manifest·아이콘·메일 PNG.

실행: uv run python -m tests.web.check_design
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from tests.web import common

from sqlalchemy import delete, select  # noqa: E402

import db  # noqa: E402
from pipeline import persist  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"

A = "web-design-a@toolscout.test"
HOST = "https://example.test/web-design/"

DAY1, DAY2, DAY3 = date(2000, 1, 11), date(2000, 1, 12), date(2000, 1, 13)
RUN_STATS_1 = {"selected": 50, "rejected": 1, "excluded": 0, "verify_requested": 2, "verified": 0}
RUN_STATS_2 = {"selected": 0, "rejected": 1, "excluded": 0, "verify_requested": 0, "verified": 0}


def card(n: int, url: str) -> dict:
    return {"type": "mcp", "title": f"검수 카드 {n}", "url": url, "summary_ko": f"요약 {n}", "for_me": f"나한테는 {n}",
            "why_this_card": f"이유 {n}", "source_checked": True, "notice": None, "relevance": 4,
            "pros": [], "cons": [], "install_cmd": "npx -y x", "trace_id": f"t-design-{n}"}


def item(n: int) -> dict:
    return {"type": "mcp", "topic": "mcp_tools", "source": "mcp_registry", "stars": 1240, "version": "1.1.1",
            "published_at": "2026-09-13T10:00:00+09:00", "summary": f"설명 {n}"}


def cleanup() -> None:
    with db.get_engine().begin() as c:
        ids = [r[0] for r in c.execute(select(db.Item.id).where(db.Item.url.like(f"{HOST}%")))]
        common.cleanup_users("web-design-")
        if ids:
            c.execute(delete(db.Item).where(db.Item.id.in_(ids)))


def check_a() -> dict:
    """읽기 전용 API 검수(persist.save_user 직접 호출, HTTP는 조회만)."""
    with common.client() as c:
        common.login(c, A)
        user_id = common.user_id(A)
        url1, url3 = f"{HOST}1", f"{HOST}3"
        persist.save_user(user_id, DAY1, [card(1, url1)], {url1: item(1)},
                           trace_id="t-design", pool_size=178, run_stats=RUN_STATS_1)
        persist.save_user(user_id, DAY2, [], {}, empty_reason="검수 빈 날", trace_id="t-empty", run_stats=RUN_STATS_2)
        persist.save_user(user_id, DAY3, [card(3, url3)], {url3: item(3)}, trace_id="t-design-3")

        data1 = c.get(f"/api/briefings?date={DAY1}").json()
        data2 = c.get(f"/api/briefings?date={DAY2}").json()
        data3 = c.get(f"/api/briefings?date={DAY3}").json()

    cards1 = data1["cards"]
    return {
        "A_run_stats_저장값_그대로": data1["run_stats"] == RUN_STATS_1,
        "A_item_meta_필드": bool(cards1) and cards1[0]["item_meta"] == {
            "stars": 1240, "version": "1.1.1", "source": "mcp_registry", "published_at": "2026-09-13T01:00:00Z"},
        "A_건수_풀사이즈_피드백": data1["count"] == 1 and data1["pool_size"] == 178 and bool(cards1) and "feedback" in cards1[0],
        "A_빈날_run_stats_저장": data2["count"] == 0 and data2["empty_reason"] == "검수 빈 날" and data2["run_stats"] == RUN_STATS_2,
        "A_run_stats_없으면_None": data3["run_stats"] is None,
    }


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


# 이모지 범위(자모·기호용 U+2600~27BF 포함). ★(U+2605)는 참고 파일에 있어 허용한다
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
ALLOWED_EMOJI = chr(0x2605)
LONG_DASH = chr(0x2014)
# 토큰 밖에 있으면 안 되는 색 표기(2026-10-14: hex에 더해 rgb·hsl 함수와 색 이름 white·black)
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|(?<![\w-])(?:white|black)(?![\w-])")
NEW_TOKENS = ["--line-ctl", "--focus", "--rule", "--fs-sm", "--s-4", "--dur-base", "--z-sheet"]
ICON_KEYS = {"ok", "bad", "warn", "na", "key", "shield", "risk", "clock", "ext", "copy", "star", "flag", "mute", "tried", "chev", "chat", "today", "history",
             "settings", "approve", "search", "logout", "arrow", "back", "eye", "mail", "close", "filter", "refresh", "up", "play", "lock", "info", "wait", "mark"}
CARD_PAGES = ["index.html", "demo.html", "history.html", "login.html"]
# 대비 기준(디자인 회의 4장 4-1): 글자 4.5, 누르는 것 경계·포커스·괘선 3, 카드 선/면 1.5
SURFACES = ["--bg", "--surface", "--surface-2"]
TEXT_PAIRS = [(f, b) for f in ["--ink", "--ink-2", "--mute", "--blaze"] for b in SURFACES] + [
    ("--blaze-ink", "--blaze-wash"), ("--ink", "--blaze-wash"), ("--ok", "--surface"), ("--ok", "--ok-wash"), ("--warn", "--surface"), ("--warn", "--warn-wash"),
    ("--bad", "--surface"), ("--bad", "--bad-wash"), ("--on-ink", "--ink"), ("--on-ink", "--blaze"), ("--ink", "--mark")]
EDGE_PAIRS = [(f, b) for f in ["--line-ctl", "--line-input", "--focus"] for b in SURFACES] + [
    ("--blaze", "--blaze-wash"), ("--rule", "--surface")]  # --hl-border는 2026-10-15 2라운드에 지웠다(큰 소식 위 2px 괘선 없음)
LINE_PAIRS = [("--line", "--surface"), ("--line", "--bg")]  # 뉴스가 상자 없이 바탕 위 괘선 목록이 되어 line/bg도 1.5(2라운드 2-1)
SVG_BUDGET = 8 * 1024
PNG_BUDGET = {"icons/icon-192.png": (192, 192, 10), "icons/icon-512.png": (512, 512, 30), "icons/apple-touch-icon.png": (180, 180, 10),
              "img/mail/mark-56.png": (56, 56, 15), "img/mail/empty-192.png": (192, 144, 15)}  # 이름: (폭, 높이, KB 상한)


def has_emoji(text: str) -> bool:
    return any(ch != ALLOWED_EMOJI for ch in EMOJI.findall(text))


def has_uppercase_transform(text: str) -> bool:
    squashed = re.sub(r"\s+", "", text).lower()
    return "text-transform:uppercase" in squashed


def strip_tokens(css: str) -> str:
    """:root{...} 토큰 블록(라이트·다크·수동 다크)을 뺀 나머지 규칙."""
    return re.sub(r":root[^{}]*\{[^}]*\}", "", css)


def block(css: str, selector: str) -> dict[str, str]:
    """선택자 바로 뒤 { } 안의 선언을 {이름: 값}으로 (주석 뺌, 공백 정리)."""
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S) if m else ""
    pairs = [d.split(":", 1) for d in body.split(";") if ":" in d]
    return {k.strip(): re.sub(r"\s+", " ", v.strip()) for k, v in pairs}


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return round((hi + 0.05) / (lo + 0.05), 2)


def contrast_fails(tokens: dict[str, str]) -> list[str]:
    """기준을 못 넘는 쌍 목록. 값이 hex가 아니거나 없으면 그것도 실패로 적는다."""
    fails = []
    for pairs, need in ((TEXT_PAIRS, 4.5), (EDGE_PAIRS, 3.0), (LINE_PAIRS, 1.5)):
        for f, b in pairs:
            fv, bv = tokens.get(f, ""), tokens.get(b, "")
            if not (re.fullmatch(r"#[0-9A-Fa-f]{6}", fv) and re.fullmatch(r"#[0-9A-Fa-f]{6}", bv)) or contrast(fv, bv) < need:
                fails.append(f"{f}/{b}")
    return fails


def check_b() -> dict:
    """화면 파일 정적 검사 (공통 체계: app.css 토큰 + cards.css + 앱 셸 app.js, 2026-10-14 2차 리디자인으로 범위를 넓힘)."""
    app_css = read(WEB / "app.css")
    css_files = [WEB / "app.css", WEB / "cards.css", WEB / "profile.css"]
    css_all = "\n".join(read(f) for f in css_files)
    html_files = sorted(WEB.glob("*.html"))
    html_texts = {f.name: read(f) for f in html_files}
    html_styles = "\n".join(s for t in html_texts.values() for s in re.findall(r"<style[^>]*>(.*?)</style>", t, re.S))
    rules = strip_tokens(css_all + "\n" + html_styles)

    light = block(app_css, ":root")
    dark_auto = block(app_css, ':root:not([data-theme="light"])')
    dark_manual = block(app_css, ':root[data-theme="dark"]')
    token_values = list(light.values()) + list(dark_auto.values()) + list(dark_manual.values())
    tokens_ok = all(t in app_css for t in ["--bg:", "--surface:", "--ink:", "--blaze:", "--ok:", "--warn:", "--bad:", "--line:"])
    components_ok = all(c in app_css for c in [".appbar", ".tabs", ".tabbar", ".btn", ".input", ".alert", ".pill", ".savebar", ".confirm-line",
                                                ".mark{", ".ill{", ".ill-lg{", ".tagline{", ".pill-pass", ".pill-plain", ".pill-bad", ".pill-warn", "@starting-style"])
    topic_rules_ok = ".topic" in css_all and "--t:" not in css_all  # 주제 10색은 없앴다(글자 칩 하나)

    def in_every_html(check) -> bool:
        return bool(html_texts) and all(check(t) for t in html_texts.values())

    def head(t: str) -> str:
        return t.split("</head>", 1)[0]

    app_js_text = read(WEB / "app.js")
    icons_block = app_js_text.split("ICONS: {", 1)[1].split("\n  },", 1)[0] if "ICONS: {" in app_js_text else ""
    app_js_ok = bool(app_js_text) and all(
        s in app_js_text for s in ["aria-current", "DEV", 'class="tabs"', "async shell(", "bare(", "data-logout", "confirmLine(", 'href="#i-mark"', "회 남음"])
    cards_js_text = read(WEB / "cards.js")
    cards_js_needles = ["readonly", "aria-pressed", "muted", "forme", "trace", "pipe", "verify", "cmd", "tool", "news", "mount("]
    cards_js_ok = bool(cards_js_text) and all(n in cards_js_text for n in cards_js_needles)

    web_texts = [read(f) for f in sorted(WEB.glob("*.html")) + sorted(WEB.glob("*.js")) + sorted(WEB.glob("*.css"))]
    svgs = sorted((WEB / "img").rglob("*.svg")) + sorted((WEB / "icons").glob("*.svg"))
    svg_safe = bool(svgs) and not any(re.search(r"<script|\son\w+\s*=|href=\"http", read(f), re.I) for f in svgs)
    svg_budget = all(f.stat().st_size <= SVG_BUDGET for f in svgs) and (WEB / "img" / "illus.svg").exists() \
        and sum(f.stat().st_size for f in (WEB / "img").rglob("*.svg")) <= 24 * 1024
    cases_file = json.loads(read(ROOT / "tests" / "web" / "verdict_cases.json") or "{}")
    cases, head_cases = cases_file.get("cases", []), (cases_file.get("tool_head") or {}).get("cases", [])
    illus = read(WEB / "img" / "illus.svg")

    return {
        "B_app_css_토큰_라이트": tokens_ok,
        "B_app_css_다크_자동·수동": bool(dark_auto) and bool(dark_manual) and "prefers-color-scheme" in app_css,
        "B_다크_자동==수동(선언_집합)": bool(dark_auto) and dark_auto == dark_manual,
        "B_새_토큰_존재": all(f"{t}:" in app_css for t in NEW_TOKENS) and all(t in light for t in NEW_TOKENS),
        "B_제호_크기_토큰_--fs-4xl(2.25rem)": light.get("--fs-4xl") == "2.25rem",
        "B_--hl-border_이름_없음(css·html_style)": "--hl-border" not in css_all + html_styles,
        "B_토큰_값에_var()_없음": bool(token_values) and not any("var(" in v for v in token_values),
        "B_대비_라이트(글자4.5·경계3·선1.5)": not contrast_fails(light),
        "B_대비_다크(글자4.5·경계3·선1.5)": not contrast_fails({**light, **dark_manual}),
        "B_app_css_공통_컴포넌트": components_ok,
        "B_app_css_cards_import_없음": "@import" not in app_css,
        "B_css_주제_글자칩(10색_없음)": topic_rules_ok,
        "B_css·html_style_토큰_밖_색값_없음": not COLOR.findall(rules),
        "B_css·html_style_keyframes_없음": "@keyframes" not in css_all + html_styles,
        "B_svg_스크립트·이벤트·외부링크_없음": svg_safe,
        "B_svg_크기_예산(8KB·그림_24KB)": svg_budget,
        "B_illus_dawn_symbol·<text_없음": '<symbol id="dawn" viewBox="0 0 160 120"' in illus and "<text" not in illus,
        "B_html_뷰포트": in_every_html(lambda t: 'name="viewport"' in t),
        "B_html_pretendard_CDN": in_every_html(lambda t: "pretendard" in t.lower()),
        "B_html_jetbrains_CDN": in_every_html(lambda t: "@fontsource-variable/jetbrains-mono@5.3.0/index.css" in head(t)),
        "B_html_preconnect": in_every_html(lambda t: '<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>' in head(t)),
        "B_html_app_css_링크": in_every_html(lambda t: "/static/app.css" in t),
        "B_html_카드_화면_cards_css_링크": all('<link rel="stylesheet" href="/static/cards.css">' in head(html_texts.get(n, "")) for n in CARD_PAGES),
        "B_html_파비콘_svg·apple_touch": in_every_html(lambda t: '<link rel="icon" type="image/svg+xml" href="/static/icons/icon.svg">' in head(t)
                                                       and '<link rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png">' in head(t)),
        "B_html_상단바_자리": in_every_html(lambda t: 'id="appbar"' in t),
        "B_html_manifest_링크": in_every_html(lambda t: '<link rel="manifest" href="/static/manifest.json">' in t),
        "B_html_theme_color": in_every_html(lambda t: '<meta name="theme-color" content="#15181E">' in t),
        "B_index_요소": "cards.js" in html_texts.get("index.html", ""),
        "B_app_js_요소": app_js_ok,
        "B_app_js_Lucide_고지_둘째_줄": app_js_text.splitlines()[1:2] == ["/*! Lucide 1.57.0 (ISC) https://lucide.dev, 일부 Feather (MIT). 고지 전문: docs/licenses/lucide.txt */"]
        and (ROOT / "docs" / "licenses" / "lucide.txt").exists(),
        "B_app_js_아이콘_키_35개": set(re.findall(r"(?:^|\s)(\w+): '<", icons_block)) == ICON_KEYS,
        "B_cards_js_요소": cards_js_ok,
        "B_판정_사례_파일": len(cases) >= 15 and all({"id", "card", "badge"} <= set(c) for c in cases),
        "B_도구_머리_사례(tool_head_5개_이상)": len(head_cases) >= 5 and all({"id", "cards", "text"} <= set(c) for c in head_cases),
        "B_이모지_없음": bool(web_texts) and not any(has_emoji(t) for t in web_texts),
        "B_text_transform_uppercase_없음": bool(web_texts) and not any(has_uppercase_transform(t) for t in web_texts),
        "B_긴줄표_없음": bool(web_texts) and not any(LONG_DASH in t for t in web_texts),
    }


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def check_c() -> dict:
    """PWA manifest·아이콘·메일 그림 파일 검사. 바탕색은 app.css 라이트 --bg와 같아야 한다."""
    manifest_path = WEB / "manifest.json"
    manifest_data: dict = {}
    manifest_is_json = False
    if manifest_path.exists():
        try:
            manifest_data = json.loads(read(manifest_path))
            manifest_is_json = True
        except json.JSONDecodeError:
            manifest_is_json = False
    bg = block(read(WEB / "app.css"), ":root").get("--bg")

    manifest_fields_ok = manifest_is_json and all([
        manifest_data.get("name") == "toolscout",
        manifest_data.get("start_url") == "/",
        manifest_data.get("display") == "standalone",
        manifest_data.get("theme_color") == "#15181E",
        bool(bg) and manifest_data.get("background_color") == bg,
    ])

    icons = manifest_data.get("icons") or [] if manifest_is_json else []
    icon_names = {Path(str(i.get("src", ""))).name for i in icons}
    icon192, icon512 = WEB / "icons" / "icon-192.png", WEB / "icons" / "icon-512.png"
    icons_exist = icon_names == {"icon-192.png", "icon-512.png"} and icon192.exists() and icon512.exists()
    purpose_ok = bool(icons) and all(set(str(i.get("purpose", "any")).split()) <= {"any", "maskable"} for i in icons)

    icons_size_ok = False
    if icon192.exists() and icon512.exists():
        icons_size_ok = png_size(icon192) == (192, 192) and png_size(icon512) == (512, 512)
    pngs_ok = all((WEB / n).exists() and png_size(WEB / n) == (w, h) and (WEB / n).stat().st_size <= kb * 1024
                  and (WEB / n).read_bytes()[25] in (0, 2) for n, (w, h, kb) in PNG_BUDGET.items())  # 색 형식 회색·RGB = 알파 없음(투명 금지)

    return {
        "C_manifest_JSON": manifest_is_json,
        "C_manifest_필드(바탕=라이트_--bg)": manifest_fields_ok,
        "C_아이콘_경로_파일_존재": icons_exist,
        "C_아이콘_purpose(any·maskable)": purpose_ok,
        "C_아이콘_크기_정확": icons_size_ok,
        "C_아이콘·메일_PNG_크기·예산·불투명": pngs_ok,
    }


def main() -> int:
    cleanup()
    try:
        checks_a = check_a()
    finally:
        cleanup()
    checks = {**checks_a, **check_b(), **check_c()}
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
