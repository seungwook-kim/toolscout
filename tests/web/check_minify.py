"""배포용 경량화(minify_web.py) 검수 (2026-10-09). 모델 호출 없음. 저장소 원본 web/은 건드리지 않는다.

실행: uv run python -m tests.web.check_minify   (Edge 필요, uv가 minify-html·rcssmin을 임시로 받는다)
1. 저장소 파일을 임시 폴더에 복사해 `minify_web.py`를 실제 배포 명령으로 돌린다 (크기 줄었는지, `/*!` 고지가 남았는지)
2. 줄인 모든 JS와 HTML 인라인 스크립트를 `node --check`, 화면당 CSS(그 HTML의 /static/*.css + 인라인 style, 줄인 결과) 42KB·gzip 10KB 이하(2026-10-15)
3. 줄인 폴더로 앱을 8002번에 띄우고(SCHEDULER_ENABLED=0) Edge 헤드리스로 공개 화면(/login /signup /demo)과
   관리자 로그인 뒤 화면(/ /history /settings /admin/invites /onboarding)을 열어 콘솔 오류가 없는지 본다
   로그인은 서명 링크 /auth/verify (토큰·비밀값은 출력하지 않는다). 끝나면 서버·Edge를 끄고 임시 폴더를 지운다
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import httpx

import config  # noqa: F401  (.env 로드)
from routes import tokens

ROOT = Path(__file__).resolve().parents[2]
PORT, DEBUG_PORT = 8002, 9223
BASE = f"http://127.0.0.1:{PORT}"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
NOTICE = "/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */"
PUBLIC = ["/login", "/signup", "/demo"]
ADMIN_PAGES = ["/", "/history", "/settings", "/admin/invites", "/onboarding"]
CSS_PAGE_MAX, CSS_PAGE_GZIP_MAX = 42 * 1024, 10 * 1024  # 화면당 CSS 예산(디자인 회의 2라운드 4장 2-3). 넘으면 새 규칙 전에 같은 양을 지운다


def copy_repo(dest: Path) -> None:
    """git이 아는 파일(추적 + 무시 안 된 새 파일)과 .env를 복사한다. 앱을 띄우는 데 필요하다."""
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
    for name in files + [".env"]:
        src = ROOT / name
        if src.is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / name)


def node_check(code_files: dict[str, str], work: Path) -> list[str]:
    bad = []
    for name, code in code_files.items():
        target = work / (re.sub(r"\W", "_", name) + ".js")
        target.write_text(code, encoding="utf-8")
        out = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            bad.append(f"{name}: {out.stderr.strip().splitlines()[-1] if out.stderr.strip() else '?'}")
    return bad


def inline_scripts(web: Path) -> dict[str, str]:
    found = {}
    for page in sorted(web.glob("*.html")):
        for i, match in enumerate(re.finditer(r"<script\b([^>]*)>(.*?)</script>", page.read_text(encoding="utf-8"), re.S)):
            if "src=" not in match.group(1) and match.group(2).strip():
                found[f"{page.name}#{i}"] = match.group(2)
    return found


def css_per_page(web: Path) -> dict[str, list[int]]:
    """화면당 CSS 예산(2026-10-15 2라운드 2-3): 그 HTML이 읽는 /static/*.css + 인라인 <style>을 줄인 결과물로 더한 [바이트, gzip 바이트]."""
    sizes = {}
    for page in sorted(web.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        names = [m.group(1) for tag in re.findall(r"<link\b[^>]*>", html) if re.search(r"rel=[\"']?stylesheet", tag)
                 for m in [re.search(r"href=[\"']?/static/([\w.-]+\.css)", tag)] if m]
        css = "".join((web / n).read_text(encoding="utf-8") for n in names if (web / n).is_file())
        data = (css + "".join(re.findall(r"<style\b[^>]*>(.*?)</style>", html, re.S))).encode("utf-8")
        sizes[page.name] = [len(data), len(gzip.compress(data, 9))]
    return sizes


def wait_health() -> bool:
    for _ in range(100):
        try:
            if httpx.get(f"{BASE}/api/health", timeout=1).status_code == 200:
                return True
        except httpx.HTTPError:
            time.sleep(0.3)
    return False


def stop(proc: subprocess.Popen | None) -> None:
    if proc is not None and proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)  # 내가 띄운 프로세스 트리만


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="toolscout_minify_"))
    app_dir, edge_profile = tmp / "app", tmp / "edge"
    app_dir.mkdir()
    server = edge = None
    try:
        copy_repo(app_dir)
        original = {p.name: p.stat().st_size for p in (app_dir / "web").glob("*") if p.suffix in (".html", ".js", ".css")}
        run = subprocess.run(["uv", "run", "--with", "minify-html", "--with", "rcssmin", "python", "minify_web.py", str(app_dir)],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        web = app_dir / "web"
        minified = {p.name: p.stat().st_size for p in web.glob("*") if p.suffix in (".html", ".js", ".css")}
        js_files = {p.name: p.read_text(encoding="utf-8") for p in sorted(web.glob("*.js"))}
        inline = inline_scripts(web)
        syntax_errors = node_check({**js_files, **inline}, tmp)
        css_js = [p for p in web.glob("*") if p.suffix in (".js", ".css")]
        css_pages = css_per_page(web)
        css_over = {n: s for n, s in css_pages.items() if s[0] > CSS_PAGE_MAX or s[1] > CSS_PAGE_GZIP_MAX}
        results: list[dict] = []
        if run.returncode == 0 and not syntax_errors:
            env = os.environ | {"SCHEDULER_ENABLED": "0", "APP_BASE_URL": BASE, "PYTHONDONTWRITEBYTECODE": "1"}
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
                                      cwd=app_dir, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if wait_health():
                admin = next(e.strip() for e in os.environ["ADMIN_EMAILS"].split(",") if e.strip())
                link = f"{BASE}/auth/verify?token={quote(tokens.sign('login', {'email': admin}, 600))}"
                edge = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={edge_profile}",
                                         "--no-first-run", "--disable-gpu", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(50):
                    try:
                        httpx.get(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
                        break
                    except httpx.HTTPError:
                        time.sleep(0.3)
                driver = ROOT / "tests" / "web" / "cdp_console.mjs"
                out = subprocess.run(["node", "--experimental-websocket", str(driver), str(DEBUG_PORT), BASE, *PUBLIC, f"LOGIN={link}", *ADMIN_PAGES],
                                     capture_output=True, text=True, encoding="utf-8", timeout=180)
                results = [json.loads(line) for line in out.stdout.splitlines() if line.startswith("{")]
        screens = {r["path"]: not r["errors"] and r["bodyChars"] > 20 for r in results}
        checks = {
            "경량화_명령_성공": run.returncode == 0,
            "HTML·CSS_파일마다_작아짐": bool(minified) and all(minified[n] < original[n] for n in minified if not n.endswith(".js")),
            "JS_파일_그대로(템플릿 문자열 보호)": all(js_files[n] == (ROOT / "web" / n).read_text(encoding="utf-8") for n in js_files),
            "JS·CSS_첫머리_고지_남음": bool(css_js) and all(p.read_text(encoding="utf-8").startswith(NOTICE) for p in css_js),
            "HTML_고지·tdm_meta_남음": all("© 2026 toolscout" in p.read_text(encoding="utf-8") and "tdm-reservation" in p.read_text(encoding="utf-8")
                                       for p in web.glob("*.html")),
            "node_check_통과": not syntax_errors and len(js_files) >= 4 and len(inline) >= 8,
            "화면당_CSS_예산(minify_42KB·gzip_10KB)": bool(css_pages) and not css_over,
            "화면_모두_열림": len(results) == len(PUBLIC) + len(ADMIN_PAGES),
            "공개_화면_콘솔_오류_없음": all(screens.get(p) for p in PUBLIC),
            "관리자_화면_콘솔_오류_없음": all(screens.get(p) for p in ADMIN_PAGES),
            "관리자_로그인됨": any(r["path"] == "/admin/invites" and r["final"] == "/admin/invites" for r in results),
        }
        print(json.dumps({"checks": checks, "css_per_page": css_pages, "css_over_budget": css_over, "screens": results, "node_check_errors": syntax_errors, "minify_tail": run.stdout.strip().splitlines()[-1:],
                          "minify_stderr": run.stderr.strip()[-300:]}, ensure_ascii=False, indent=2))
        ok = all(checks.values())
        print("통과" if ok else "실패")
        return 0 if ok else 1
    finally:
        stop(edge)
        stop(server)
        time.sleep(1)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
