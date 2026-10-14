"""화면 자동 검수 (2026-10-14 2차 리디자인, 디자인 회의 4장 4-5 + 2026-10-15 2라운드 2-4). 모델 호출 없음, 메일은 가짜 폴더(MAIL_FAKE_DIR)만.

실행: uv run python -m tests.web.check_screens [스크린샷 폴더] [--only today,login]   (Edge·node 필요. 기본 폴더는 임시 폴더, --only(=)는 화면 일부만)
앱을 8013번에 띄우고(SCHEDULER_ENABLED=0) Edge 헤드리스 원격 디버깅으로 화면 전부 × 라이트·자동 다크·수동 다크(data-theme="dark") × 1366(높이 650)·390·360을 연다.
Edge·앱은 한 번만 띄우고 node(cdp_screens.mjs)는 화면마다 따로 돌린다(쿠키 지움 → 필요하면 서명 로그인 링크 → 그 화면). 한 번에 240초, 넘으면 그 화면에 timeout 1건.
390·360은 mobile + 터치 흉내(pointer:coarse). 공개 화면 → 승인 대기 검수 사용자(/pending) → 첫 설정 검수 사용자(/onboarding) → 관리자 화면 →
데이터 없는 검수 사용자(직군 있음)로 오늘 '아직 없음'(today_none), 같은 사용자에게 빈 날 행을 저장하고 카드 0장(today_zero).
항목(모두 0건이면 통과): 1 가로 넘침 2 콘솔 오류 3 글자 대비 4 누르는 것 테두리 대비 5 글자 크기 6 터치 44(폰) 6-1 카드 버튼 줄 한 줄(360)
7 포커스 링 3:1 8 움직임 줄이기 9 판정 배지·도구 머리 글(tests/web/verdict_cases.json을 데모 화면의 Cards.badge·Cards.toolHead로)
10 잘림(세로로 넘치는데 잘라 내거나 자체 스크롤) 11 flex 맨 글자(gap 있는 flex·grid에서 맨 글자와 span 등이 형제) 브랜드(1장 2판 검수 1·2·4·5) timeout
출력: 조합마다 JSON 한 줄(실패만 줄임) + 마지막에 항목별 건수·화면별 걸린 초·pass. 스크린샷 <폴더>/<화면>_<폭>(_dark|_mdark).png
검수 사용자 web-screens-*@toolscout.test는 만들고 끝에 지운다(브리핑 행 포함). 토큰·비밀값은 출력하지 않는다.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

import config  # noqa: F401  (.env 로드)
from tests.web import common  # 예약 끔·가짜 메일 폴더를 환경에 넣는다(띄우는 앱도 물려받음)

from sqlalchemy import select  # noqa: E402

import db  # noqa: E402
from pipeline import persist  # noqa: E402
from routes import tokens  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PORT, DEBUG_PORT = 8013, 9234
BASE = f"http://127.0.0.1:{PORT}"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
WAIT_USER, FIRST_USER = "web-screens-wait@toolscout.test", "web-screens-first@toolscout.test"
EMPTY_USER = "web-screens-empty@toolscout.test"  # 승인·직군 있음, 오늘 브리핑 없음 → today_none, 빈 날 행 저장 뒤 → today_zero
ITEMS = ["overflow", "console", "contrast", "border", "size", "touch", "cfoot", "focus", "motion", "clip", "flextext", "brand"]
LABELS = {"cfoot": "6-1", "focus": "7", "motion": "8", "clip": "10", "flextext": "11", "brand": "브랜드"}
RUN_TIMEOUT = 240
PUBLIC = [("login", "/login"), ("signup", "/signup"), ("demo", "/demo"), ("policy", "/policy"), ("privacy", "/privacy"),
          ("terms", "/terms"), ("support", "/support"), ("f", "/f")]
PRIVATE = [("today", "/"), ("history", "/history"), ("settings", "/settings"), ("admin", "/admin/invites")]
TAGLINE = {"login", "signup", "demo"}  # 워드마크 옆 설명이 있는 화면(1장 2판 1-2(f)). 앱 상단바(shell) 화면에는 없어야 한다


def screens() -> list[dict]:
    """화면 목록(순서대로). who: 로그인할 검수 사용자(None이면 쿠키만 지움), brand: 화면 안 브랜드 검수 표시."""
    out = [{"name": n, "path": p, "who": None, "wait": 2500, "verdict": n == "demo",
            "brand": {"tagline": n in TAGLINE, "oneIll": n == "login"}} for n, p in PUBLIC]
    out += [{"name": "pending", "path": "/pending", "who": WAIT_USER, "wait": 2500, "brand": {"app": True}},
            {"name": "onboarding", "path": "/onboarding", "who": FIRST_USER, "wait": 3000, "brand": {"app": True}}]
    out += [{"name": n, "path": p, "who": "admin", "wait": 3500, "brand": {"app": True}} for n, p in PRIVATE]
    out += [{"name": "today_none", "path": "/", "who": EMPTY_USER, "wait": 3000, "brand": {"app": True, "dawn": True}},
            {"name": "today_zero", "path": "/", "who": EMPTY_USER, "wait": 3000, "brand": {"app": True, "zero": True}, "empty_day": True}]
    return out


def link(email: str) -> str:
    return f"{BASE}/auth/verify?token={quote(tokens.sign('login', {'email': email}, 900))}"


def make_users() -> None:
    """승인 대기(pending), 승인됐지만 직군이 빈(첫 설정), 승인·직군 있고 브리핑이 없는(오늘 빈 상태) 검수 사용자."""
    common.cleanup_users("web-screens-")
    with db.session() as s:
        s.add(db.User(email=WAIT_USER, role="", status="pending", is_test=True))
        s.add(db.User(email=FIRST_USER, role="", status="approved", is_test=True))
        s.add(db.User(email=EMPTY_USER, role="개발자", status="approved", is_test=True))
        s.commit()


def save_empty_day() -> None:
    """EMPTY_USER의 오늘(KST)에 빈 날 행 하나(카드 0장, empty_reason). 끝에 cleanup_users가 briefings까지 지운다."""
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    persist.save_user(common.user_id(EMPTY_USER), today, [], {}, empty_reason="검수: 후보를 살펴봤지만 기준에 맞는 카드가 없음",
                      trace_id="t-screens-zero", run_stats={"selected": 0, "rejected": 3, "excluded": 0, "verify_requested": 0, "verified": 0})


def wait_url(url: str, tries: int = 100) -> bool:
    for _ in range(tries):
        try:
            httpx.get(url, timeout=1)
            return True
        except httpx.HTTPError:
            time.sleep(0.3)
    return False


def stop(proc: subprocess.Popen | None) -> None:
    if proc is not None and proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)  # 내가 띄운 프로세스 트리만


def verdict_fails(got: list, cases: list) -> list[str]:
    expected = {c["id"]: c["badge"] for c in cases}
    if not got:
        return ["판정 결과 없음(데모 화면을 못 엶)"]
    return [f"{g.get('id')}: {g.get('error') or g.get('got')} != {expected.get(g.get('id'))}" for g in got
            if "error" in g or g.get("got") != expected.get(g.get("id"))][:12]


def tool_head_fails(got: list, cases: list) -> list[str]:
    """Cards.toolHead(카드 배열)의 글자(태그 뺀 textContent)가 사례의 text와 같은지."""
    expected = {c["id"]: c["text"] for c in cases}
    if not got:
        return ["도구 머리 결과 없음(데모 화면을 못 엶)"]
    return [f"tool_head {g.get('id')}: {g.get('error') or g.get('got')!r} != {expected.get(g.get('id'))!r}" for g in got
            if "error" in g or g.get("got") != expected.get(g.get("id"))][:12]


def text_of(value) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else (value or "")


def run_screen(screen: dict, admin: str, job_base: dict, tmp: Path) -> tuple[list[dict], dict, float, str]:
    """화면 하나를 node 한 번으로. 반환: (조합 줄들, {verdict, tool_head}, 걸린 초, 오류 글)."""
    steps: list[dict] = [{"clear": True}]
    who = admin if screen["who"] == "admin" else screen["who"]
    if who:
        steps.append({"login": link(who)})
    steps.append({"name": screen["name"], "url": BASE + screen["path"], "wait": screen["wait"], "verdict": screen.get("verdict", False),
                  "brand": screen.get("brand", {})})
    spec = tmp / f"job_{screen['name']}.json"
    spec.write_text(json.dumps({**job_base, "steps": steps}, ensure_ascii=False), encoding="utf-8")
    t0, error = time.monotonic(), ""
    try:
        run = subprocess.run(["node", "--experimental-websocket", str(ROOT / "tests" / "web" / "cdp_screens.mjs"), str(DEBUG_PORT), str(spec)],
                             capture_output=True, text=True, encoding="utf-8", timeout=RUN_TIMEOUT)
        stdout, stderr = run.stdout, run.stderr
        if run.returncode != 0:
            error = f"node 종료 코드 {run.returncode}: {stderr.strip()[-400:]}"
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, error = text_of(exc.stdout), text_of(exc.stderr), f"timeout {RUN_TIMEOUT}초"
    rows, extra = [], {}
    for line in stdout.splitlines():
        if not line.startswith("{"):
            continue
        data = json.loads(line)
        if "verdict" in data or "tool_head" in data:
            extra.update(data)
        elif "screen" in data:
            rows.append(data)
    return rows, extra, round(time.monotonic() - t0, 1), error


def main() -> int:
    argv, args, only = sys.argv[1:], [], set()
    for i, a in enumerate(argv):  # --only=a,b 와 --only a,b 둘 다 받는다
        if a.startswith("--only="):
            only |= set(a.split("=", 1)[1].split(","))
        elif a == "--only" and i + 1 < len(argv):
            only |= set(argv[i + 1].split(","))
        elif not (i > 0 and argv[i - 1] == "--only"):
            args.append(a)
    only.discard("")
    out = Path(args[0]).resolve() if args else Path(tempfile.mkdtemp(prefix="ts_screens_"))
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ts_check_screens_"))
    cases_file = json.loads((ROOT / "tests" / "web" / "verdict_cases.json").read_text(encoding="utf-8"))
    cases, head_cases = cases_file["cases"], cases_file.get("tool_head", {}).get("cases", [])
    chosen = [s for s in screens() if not only or s["name"] in only]
    server = edge = None
    rows: list[dict] = []
    extra: dict = {}
    seconds: dict[str, float] = {}
    timeouts: list[str] = []
    make_users()
    try:
        env = os.environ | {"SCHEDULER_ENABLED": "0", "APP_BASE_URL": BASE, "PYTHONDONTWRITEBYTECODE": "1"}
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
                                  cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_url(f"{BASE}/api/health"):
            print(json.dumps({"pass": False, "error": "앱이 뜨지 않음"}, ensure_ascii=False))
            return 1
        edge = subprocess.Popen([EDGE, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", f"--user-data-dir={tmp / 'edge'}",
                                 "--no-first-run", "--disable-gpu", "--hide-scrollbars", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_url(f"http://127.0.0.1:{DEBUG_PORT}/json/version", 50)
        admin = next(e.strip() for e in os.environ["ADMIN_EMAILS"].split(",") if e.strip() and not e.strip().endswith(common.TEST_DOMAIN))
        job_base = {"out": str(out), "cases": cases, "tool_head": head_cases}
        for screen in chosen:
            if screen.get("empty_day"):
                save_empty_day()
            got, more, secs, error = run_screen(screen, admin, job_base, tmp)
            seconds[screen["name"]] = secs
            extra.update(more)
            if error.startswith("timeout"):
                timeouts.append(screen["name"])
            if error:
                print(json.dumps({"screen": screen["name"], "error": error}, ensure_ascii=False))
            for data in got:
                rows.append(data)
                short = {k: v for k, v in data["fails"].items() if v}
                print(json.dumps({"screen": data["screen"], "width": data["width"], "theme": data["theme"], "final": data["final"], "fails": short},
                                 ensure_ascii=False))
    finally:
        stop(edge)
        stop(server)
        common.cleanup_users("web-screens-")
        time.sleep(1)
    with db.session() as s:
        left = s.exec(select(db.User.id).where(db.User.email.like("web-screens-%"))).first()
    totals = {k: sum(len(r["fails"].get(k, [])) for r in rows) for k in ITEMS}
    demo_ran = any(s["verdict"] for s in chosen if "verdict" in s)
    v_fails = verdict_fails(extra.get("verdict", []), cases) + tool_head_fails(extra.get("tool_head", []), head_cases) if demo_ran else []
    totals["verdict"], totals["timeout"] = len(v_fails), len(timeouts)
    by_screen = {s: sum(len(v) for r in rows if r["screen"] == s for v in r["fails"].values()) for s in sorted({r["screen"] for r in rows})}
    checks = {
        "조합_모두_열림": len(rows) == len(chosen) * 9,
        "검수_사용자_정리": not left,
        **{f"{LABELS.get(k, str(i + 1))}_{k}_0건": totals[k] == 0 for i, k in enumerate(ITEMS)},
        "9_verdict·tool_head_0건": totals["verdict"] == 0,
        "timeout_0건": not timeouts,
    }
    report = {"checks": checks, "totals": totals, "by_screen": by_screen, "verdict_fails": v_fails, "timeouts": timeouts, "seconds": seconds,
              "shots": str(out), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
