"""아이콘·메일 그림 PNG 굽기 (2026-10-14 2차 리디자인). 새 라이브러리 없이 Edge 헤드리스 스크린샷으로 굽는다.

실행: uv run python bake_icons.py [확인용 폴더]
- web/icons/icon-192.png·icon-512.png(앱 아이콘, any maskable: 타일을 끝까지 채우고 마크는 가운데 80% 안), apple-touch-icon.png(180)
- web/img/mail/mark-56.png(파비콘 web/icons/icon.svg를 2배로), empty-192.png(그림 #empty를 타일 위에, 192x144)
- 확인용 폴더(기본: 임시 폴더)에 파비콘 16·32px 렌더와 8배 확대본(check-16-32.png)을 남긴다. 눈으로 읽히는지 본다
색은 web/app.css 토큰에서 읽는다: 타일 --brand-tile, 선 라이트 --bg, 해(점) 다크 --blaze. 바탕은 모두 불투명이다.
"""
import base64
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def tokens() -> dict[str, str]:
    css = (WEB / "app.css").read_text(encoding="utf-8")
    light = re.search(r":root\{(.*?)\}", css, re.S).group(1)
    dark = re.search(r':root\[data-theme="dark"\]\{(.*?)\}', css, re.S).group(1)
    get = lambda block, name: re.search(rf"{name}:(#[0-9A-Fa-f]{{6}})", block).group(1)  # noqa: E731
    return {"tile": get(light, "--brand-tile"), "fg": get(light, "--bg"), "dot": get(dark, "--blaze")}


def app_icon(c: dict) -> str:
    """앱 아이콘 원본(512 격자): 타일 전체 + 마크를 10배로 가운데(내용 x 146~376, y 181~348, 중심에서 가장 먼 점 약 150px < 204.8)."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" fill="{c["tile"]}"/>'
            f'<g transform="translate(96 96) scale(10)"><path d="M5 8.5l7.5 7.5L5 23.5" fill="none" stroke="{c["fg"]}" stroke-width="3.5" '
            f'stroke-linecap="round" stroke-linejoin="round"/><rect x="15" y="21.75" width="13" height="3.5" rx="1.75" fill="{c["fg"]}"/>'
            f'<circle cx="21.5" cy="13" r="3.5" fill="{c["dot"]}"/></g></svg>')


def empty_ill(c: dict) -> str:
    """메일 빈 날 그림: illus.svg의 #empty를 타일 위에 그대로(선 = 라이트 바탕색, 점 = 다크 블레이즈)."""
    illus = (WEB / "img" / "illus.svg").read_text(encoding="utf-8")
    symbol = re.search(r'<symbol id="empty"[^>]*>(.*?)</symbol>', illus, re.S).group(1)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120" style="color:{c["fg"]};--ill-accent:{c["dot"]}">'
            f'<rect width="160" height="120" fill="{c["tile"]}"/><g fill="none" stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{symbol}</g></svg>')


def page(svg: str, w: int, h: int, bg: str) -> str:
    return (f'<!doctype html><meta charset="utf-8"><style>html,body{{margin:0;background:{bg};overflow:hidden}}'
            f'svg{{display:block;width:{w}px;height:{h}px}}</style>{svg}')


def shoot(html: str, out: Path, w: int, h: int, work: Path) -> None:
    src = work / f"{out.stem}.html"
    src.write_text(html, encoding="utf-8")
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", f"--window-size={w},{h}",
                    f"--user-data-dir={work / 'edge'}", f"--screenshot={out}", "--virtual-time-budget=1500", src.as_uri()],
                   capture_output=True, timeout=60)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def main() -> int:
    c = tokens()
    check_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ts_icons_"))
    check_dir.mkdir(parents=True, exist_ok=True)
    favicon = (WEB / "icons" / "icon.svg").read_text(encoding="utf-8")
    (WEB / "img" / "mail").mkdir(parents=True, exist_ok=True)
    jobs = [  # (출력, svg, 폭, 높이)
        (WEB / "icons" / "icon-192.png", app_icon(c), 192, 192), (WEB / "icons" / "icon-512.png", app_icon(c), 512, 512),
        (WEB / "icons" / "apple-touch-icon.png", app_icon(c), 180, 180),
        (WEB / "img" / "mail" / "mark-56.png", favicon, 56, 56), (WEB / "img" / "mail" / "empty-192.png", empty_ill(c), 192, 144),
        (check_dir / "favicon-16.png", favicon, 16, 16), (check_dir / "favicon-32.png", favicon, 32, 32),
    ]
    with tempfile.TemporaryDirectory(prefix="ts_bake_") as tmp:
        work = Path(tmp)
        for out, svg, w, h in jobs:
            shoot(page(svg, w, h, c["tile"]), out, w, h, work)
        # 확인용: 16·32px로 구운 파비콘을 밝은·어두운 탭 바탕 위에 실제 크기와 8배 확대(픽셀 그대로)로 놓는다
        src = {n: "data:image/png;base64," + base64.b64encode((check_dir / f"favicon-{n}.png").read_bytes()).decode("ascii") for n in (16, 32)}
        zoom = "".join(f'<div style="background:{bg};padding:12px;display:flex;gap:16px;align-items:center">'
                       + "".join(f'<img src="{src[n]}" width="{n}" height="{n}">' for n in (16, 32))
                       + "".join(f'<img src="{src[n]}" style="width:{n * 8}px;height:{n * 8}px;image-rendering:pixelated">' for n in (16, 32)) + "</div>"
                       for bg in ("#FFFFFF", "#202124"))
        shoot(f'<!doctype html><meta charset="utf-8"><body style="margin:0">{zoom}</body>', check_dir / "check-16-32.png", 480, 560, work)
    bad = []
    for out, _, w, h in jobs:
        size = png_size(out) if out.exists() else None
        print(f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}  {size}  {out.stat().st_size if out.exists() else 0}B")
        if size != (w, h):
            bad.append(out.name)
    print(f"확인용 확대본: {check_dir / 'check-16-32.png'}")
    if bad:
        print("크기가 틀림:", ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
