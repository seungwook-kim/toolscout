"""코드 수정 뒤 자동 재시작 검수 (2026-09-23). 가짜 git 상태·가짜 시계로 판단을 보고, 마지막에 진짜 uvicorn이 신호로 꺼지는지 본다.

실행: uv run python -m tests.pipeline.check_autorestart
- main에서 HEAD가 바뀌고 한가하면 재시작, 한 번만 / 같은 HEAD·기능 브랜치·커밋 안 한 수정이면 안 함
- 06:00~09:00, 실행·검증 중(busy), 다음 예정 작업 10분 이내면 안 함 / git 없음·AUTO_RESTART=0이면 꺼짐
- 예약 루프가 한 바퀴 돌 때 check를 부르고, 신호를 보낸 뒤에도 루프는 계속 돈다
- 실제 uvicorn(8011번 포트)이 신호로 정상 종료한다 / 끝나지 않는 연결이 열려 있으면(9/25 사고) 강제 종료로 빠져나온다(8012번)
- 신호를 보낸 뒤 정상 종료가 안 끝나면 정해진 시간 뒤 강제 종료를 부른다
DB·모델·메일을 쓰지 않는다.
"""
import asyncio
import json
import os
import subprocess
import sys
import time as systime
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from pipeline import autorestart, run_daily
from pipeline.autorestart import AutoRestart
from pipeline.scheduler import SEND_SLOTS, Scheduler

ROOT = Path(__file__).resolve().parents[2]
results: list[tuple[str, bool]] = []
forced: list[int] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 23, hour, minute, tzinfo=run_daily.KST)


def make(**repo):
    state = {"branch": "main", "head": "a" * 40, "dirty": False}
    fired = []
    r = AutoRestart(state_fn=lambda: dict(state), trigger=lambda: fired.append(1), force_exit=lambda: forced.append(1), force_after=0.05)
    state.update(repo)
    return r, state, fired


FAR = at(23, 59)

r, state, fired = make()
check("같은 HEAD면 재시작 안 함", not r.check(at(13), False, FAR) and not fired)
state["head"] = "b" * 40
check("main HEAD가 바뀌고 한가하면 재시작", r.check(at(13), False, FAR) and fired == [1])
systime.sleep(0.3)
check("신호 뒤 정상 종료가 안 끝나면 강제 종료를 부름", forced == [1])
check("한 번 보낸 뒤 다시 안 보냄", not r.check(at(13, 1), False, FAR) and fired == [1])

r, state, fired = make(head="b" * 40, branch="feat/x")
check("기능 브랜치면 안 함", r.reason(at(13), False, FAR) is None)
r, state, fired = make(head="b" * 40, dirty=True)
check("커밋 안 한 수정이 있으면 안 함", r.reason(at(13), False, FAR) is None)
r, state, fired = make(head="b" * 40)
check("06:00~09:00에는 안 함", all(r.reason(at(h, m), False, FAR) is None for h, m in ((6, 0), (7, 30), (8, 59))))
check("09:00부터는 함", r.reason(at(9, 0), False, FAR) is not None)
check("실행·검증 중이면 안 함", r.reason(at(13), True, FAR) is None)
check("다음 예정 10분 이내면 안 함", r.reason(at(11, 50), False, at(12)) is None and r.reason(at(11, 49), False, at(12)) is not None)

no_git = AutoRestart(state_fn=lambda: None, trigger=lambda: None)
check("git 없으면 꺼짐", no_git.start_head is None and no_git.reason(at(13), False, FAR) is None)
os.environ["AUTO_RESTART"] = "0"
off = AutoRestart(state_fn=lambda: {"branch": "main", "head": "a" * 40, "dirty": False}, trigger=lambda: None)
os.environ.pop("AUTO_RESTART")
check("AUTO_RESTART=0이면 꺼짐", off.start_head is None)
real = autorestart.repo_state()
check("이 저장소에서 git 상태를 읽음", bool(real and len(real["head"]) == 40))


async def loop_case() -> None:
    clock = {"now": at(13)}
    naps = []

    async def sleep(seconds: float) -> None:
        naps.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        if len(naps) >= 3:
            raise asyncio.CancelledError

    s = Scheduler(now=lambda: clock["now"], sleep=sleep)
    s.state.update(verify_done=at(13).date(), warm_done=at(13).date(), run_checked=at(13).date())
    s.state["sent_slots"][at(13).date()] = set(SEND_SLOTS)
    calls = []
    s._restart = type("R", (), {"check": lambda self, now, busy, nxt: calls.append((now, busy)) or True})()
    try:
        await s.loop()
    except asyncio.CancelledError:
        pass
    check("예약 루프가 바퀴마다 check를 부르고 신호 뒤에도 계속 돈다", len(calls) == 3 and not calls[0][1])


asyncio.run(loop_case())

APP = """
import asyncio, threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pipeline import run_daily
from pipeline.autorestart import AutoRestart

heads = iter(["a" * 40] + ["b" * 40] * 10)

@asynccontextmanager
async def lifespan(_app):
    r = AutoRestart(state_fn=lambda: {"branch": "main", "head": next(heads), "dirty": False}, force_after=3)
    async def later():
        await asyncio.sleep(WAIT)
        now = datetime(2026, 9, 25, 13, 0, tzinfo=run_daily.KST)
        r.check(now, False, now + timedelta(hours=5))
    task = asyncio.create_task(later())
    yield
    print("SHUTDOWN_CLEAN", flush=True)

app = FastAPI(lifespan=lifespan)

@app.get("/ping")
def ping():
    return {"ok": True}

@app.get("/stream")
async def stream():
    async def forever():
        while True:
            yield b"."
            await asyncio.sleep(0.5)
    return StreamingResponse(forever())
"""


def run_app(port: int, hang: bool) -> tuple[bool, bool, int | None, str]:
    """반환: (떴나, 20초 안에 끝났나, 종료 코드, 출력). hang이면 끝나지 않는 스트리밍 연결을 열어 둔다."""
    tmp = ROOT / "tests" / "pipeline" / f"_autorestart_app_{port}.py"
    tmp.write_text(APP.replace("WAIT", "4" if hang else "2"), encoding="utf-8")
    try:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", f"tests.pipeline.{tmp.stem}:app", "--host", "127.0.0.1",
                                 "--port", str(port)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        up = False
        for _ in range(20):
            try:
                up = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=1))["ok"]
                break
            except OSError:
                systime.sleep(0.3)
        if hang:
            import threading

            def hold():
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/stream", timeout=60) as resp:
                        while resp.read(1):
                            pass
                except OSError:
                    pass
            threading.Thread(target=hold, daemon=True).start()
        try:
            out, _ = proc.communicate(timeout=20)
            return up, True, proc.returncode, out
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            return up, False, None, out
    finally:
        tmp.unlink(missing_ok=True)


up, exited, code, out = run_app(8011, hang=False)
check("열린 연결이 없으면 신호로 정상 종료", up and exited and "SHUTDOWN_CLEAN" in out)
up, exited, code, out = run_app(8012, hang=True)
check("끝나지 않는 연결이 열려 있어도 3초 뒤 강제 종료(코드 3)", up and exited and code == 3 and "강제 종료" in out)

passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
