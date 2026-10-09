"""배포용 web/ 경량화 (2026-10-09). 저장소 원본은 건드리지 않고, 배포 때 임시 폴더에서만 쓴다.

실행: uv run --with minify-html --with rjsmin --with rcssmin python minify_web.py <배포 임시 폴더>
- <폴더>/web 의 *.html *.js *.css 를 제자리에서 줄인다: 주석 제거, 공백 축소(HTML 안 인라인 script·style 포함)
- `/*!`로 시작하는 저작권 고지는 남기고, HTML은 head의 고지 주석을 다시 넣는다
- 변수 이름 바꾸기(난독화)는 하지 않는다. 바꾸면 인라인 onclick 등이 깨질 수 있다
- 의존성(minify-html·rjsmin·rcssmin)은 배포 때만 쓰니 pyproject에 넣지 않는다 (docs/deploy.md)
- 줄인 결과가 깨지지 않았는지는 `uv run python -m tests.web.check_minify`가 본다(node --check + Edge 헤드리스)
"""
import re
import sys
from pathlib import Path

import minify_html
import rcssmin
import rjsmin

HTML_NOTICE = "<!-- © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 -->"
SCRIPT = re.compile(r"(<script\b([^>]*)>)(.*?)(</script>)", re.S | re.I)
STYLE = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.S | re.I)
JS_TYPES = ("", "text/javascript", "module", "application/javascript")


def min_js(code: str) -> str:
    return rjsmin.jsmin(code, keep_bang_comments=True)


def min_css(code: str) -> str:
    return rcssmin.cssmin(code, keep_bang_comments=True)


def _script(match: re.Match) -> str:
    kind = re.search(r'type\s*=\s*["\']?([^"\'\s>]*)', match.group(2) or "")
    if "src=" in match.group(2) or (kind and kind.group(1).lower() not in JS_TYPES):
        return match.group(0)
    return match.group(1) + min_js(match.group(3)) + match.group(4)


def min_html(text: str) -> str:
    # 인라인 script·style은 우리가 먼저 줄이고, minify-html은 마크업 공백·주석만 맡긴다 (안의 코드는 그대로 둔다)
    text = SCRIPT.sub(_script, text)
    text = STYLE.sub(lambda m: m.group(1) + min_css(m.group(2)) + m.group(3), text)
    out = minify_html.minify(text, minify_js=False, minify_css=False, keep_comments=False)
    # 고지 주석은 지워졌으니 tdm meta 앞에 다시 넣는다(둘 다 head 맨 앞)
    return re.sub(r"(<meta\b[^>]*tdm-reservation)", lambda m: HTML_NOTICE + m.group(1), out, count=1)


def run(root: Path) -> dict:
    web = root / "web"
    if not web.is_dir():
        raise SystemExit(f"web 폴더가 없다: {web}")
    sizes = {}
    for path in sorted(web.glob("*")):
        funcs = {".html": min_html, ".js": min_js, ".css": min_css}
        if path.suffix not in funcs:
            continue
        before = path.read_bytes()
        after = funcs[path.suffix](before.decode("utf-8")).encode("utf-8")
        path.write_bytes(after)
        sizes[path.name] = (len(before), len(after))
    return sizes


def main() -> int:
    if len(sys.argv) != 2:
        print("사용법: python minify_web.py <배포 임시 폴더>")
        return 2
    sizes = run(Path(sys.argv[1]))
    for name, (a, b) in sizes.items():
        print(f"{name:18} {a:>8} -> {b:>8}  ({100 - round(100 * b / a)}% 감소)")
    total_a, total_b = sum(a for a, _ in sizes.values()), sum(b for _, b in sizes.values())
    print(f"합계 {total_a} -> {total_b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
