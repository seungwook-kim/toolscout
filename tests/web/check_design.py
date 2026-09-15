"""화면 검수: run_stats·item_meta 읽기 API(A) + 화면 파일 정적 검사(B) + PWA manifest·아이콘(C).

A는 이미 구현된 pipeline/persist.py·routes/briefings.py·db.py 규격을 검수한다(모델 호출 없음).
B는 app.css가 docs/design-reference.html의 style 그대로이고 뒤에 붙인 보충 규칙은 토큰만 쓰는지, 화면 파일 공통 요소와 금지 사항을 본다.

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
from agent.schemas import TOPICS  # noqa: E402
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
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
ALLOWED_EMOJI = chr(0x2605)
LONG_DASH = chr(0x2014)


def has_emoji(text: str) -> bool:
    return any(ch != ALLOWED_EMOJI for ch in EMOJI.findall(text))


def has_uppercase_transform(text: str) -> bool:
    squashed = re.sub(r"\s+", "", text).lower()
    return "text-transform:uppercase" in squashed


def check_b() -> dict:
    """화면 파일 정적 검사."""
    ref_text = read(ROOT / "docs" / "design-reference.html")
    style_match = re.search(r"<style>\s*\n(.*?)</style>", ref_text, re.S)
    ref_style = style_match.group(1) if style_match else None

    app_css = read(WEB / "app.css")
    starts_with_ref = bool(ref_style) and app_css.startswith(ref_style)

    # 보충 부분 = 참고 style 뒤에 붙인 규칙. 참고 style 자체의 그림자·transition·:hover·색은 기준이라 검사하지 않는다
    supplement = app_css[len(ref_style):] if starts_with_ref else ""
    topic_rules_ok = bool(supplement) and all(f'[data-topic="{key}"]{{--t:var(--' in supplement for key in TOPICS)
    forbidden_in_css = ["box-shadow", "animation", "@keyframes", "transition", ":hover", "text-transform"]
    no_forbidden_css = bool(supplement) and not any(p in supplement for p in forbidden_in_css)
    hex_colors = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", supplement))
    hex_only_fff = bool(supplement) and hex_colors.issubset({"#fff"})

    html_files = sorted(WEB.glob("*.html"))
    html_texts = [read(f) for f in html_files]

    def in_every_html(needle_check) -> bool:
        return bool(html_texts) and all(needle_check(t) for t in html_texts)

    html_viewport = in_every_html(lambda t: 'name="viewport"' in t)
    html_pretendard = in_every_html(lambda t: "pretendard" in t.lower())
    html_jetbrains = in_every_html(lambda t: "jetbrains" in t.lower())
    html_app_css = in_every_html(lambda t: "/static/app.css" in t)
    html_mast = in_every_html(lambda t: '<header class="mast" id="mast">' in t)
    html_manifest_link = in_every_html(lambda t: '<link rel="manifest" href="/static/manifest.json">' in t)
    html_theme_color = in_every_html(lambda t: '<meta name="theme-color" content="#15181E">' in t)

    index_text = read(WEB / "index.html")
    index_ok = bool(index_text) and all(
        s in index_text for s in ['class="askbar"', 'class="quota"', "thread", "cards.js"])

    app_js_text = read(WEB / "app.js")
    app_js_ok = bool(app_js_text) and all(
        s in app_js_text for s in ["aria-current", 'class="mode"', "DEV", 'class="nav"'])

    cards_js_text = read(WEB / "cards.js")
    cards_js_needles = ["item", "tool", "mark", "forme", 'details class="why"', "acts", "aria-pressed", "muted",
                         "kind", "meta", "verify", "step na", "검증 예정", "cmd", "pipe", "0 검증", "empty"]
    cards_js_ok = bool(cards_js_text) and all(n in cards_js_text for n in cards_js_needles)

    js_files = [WEB / "app.js", WEB / "cards.js"]
    all_texts = html_texts + [read(f) for f in js_files] + [app_css]
    no_emoji = bool(all_texts) and not any(has_emoji(t) for t in all_texts)
    no_uppercase = bool(all_texts) and not any(has_uppercase_transform(t) for t in all_texts)
    no_long_dash = bool(all_texts) and not any(LONG_DASH in t for t in all_texts)

    return {
        "B_app_css_참고_스타일로_시작": starts_with_ref,
        "B_보충css_주제10개_규칙": topic_rules_ok,
        "B_보충css_그림자·애니메이션·호버·대문자_없음": no_forbidden_css,
        "B_보충css_새색_없음(#fff만)": hex_only_fff,
        "B_html_뷰포트": html_viewport,
        "B_html_pretendard_CDN": html_pretendard,
        "B_html_jetbrains_CDN": html_jetbrains,
        "B_html_app_css_링크": html_app_css,
        "B_html_헤더_mast": html_mast,
        "B_html_manifest_링크": html_manifest_link,
        "B_html_theme_color": html_theme_color,
        "B_index_요소": index_ok,
        "B_app_js_요소": app_js_ok,
        "B_cards_js_요소": cards_js_ok,
        "B_이모지_없음": no_emoji,
        "B_text_transform_uppercase_없음": no_uppercase,
        "B_긴줄표_없음": no_long_dash,
    }


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def check_c() -> dict:
    """PWA manifest·아이콘 파일 검사."""
    manifest_path = WEB / "manifest.json"
    manifest_data: dict = {}
    manifest_is_json = False
    if manifest_path.exists():
        try:
            manifest_data = json.loads(read(manifest_path))
            manifest_is_json = True
        except json.JSONDecodeError:
            manifest_is_json = False

    manifest_fields_ok = manifest_is_json and all([
        manifest_data.get("name") == "toolscout",
        manifest_data.get("start_url") == "/",
        manifest_data.get("display") == "standalone",
        manifest_data.get("theme_color") == "#15181E",
        manifest_data.get("background_color") == "#F7F7F4",
    ])

    icons = manifest_data.get("icons") or [] if manifest_is_json else []
    icon_names = {Path(str(i.get("src", ""))).name for i in icons}
    icon192, icon512 = WEB / "icons" / "icon-192.png", WEB / "icons" / "icon-512.png"
    icons_exist = icon_names == {"icon-192.png", "icon-512.png"} and icon192.exists() and icon512.exists()

    icons_size_ok = False
    if icon192.exists() and icon512.exists():
        icons_size_ok = png_size(icon192) == (192, 192) and png_size(icon512) == (512, 512)

    return {
        "C_manifest_JSON": manifest_is_json,
        "C_manifest_필드": manifest_fields_ok,
        "C_아이콘_경로_파일_존재": icons_exist,
        "C_아이콘_크기_정확": icons_size_ok,
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
