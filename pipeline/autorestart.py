"""코드 수정 뒤 앱 자동 재시작 (2026-09-23 사용자 요청).

예약 실행이 앱 프로세스 안에서 돌아, 코드를 고쳐 커밋해도 앱을 다시 띄우지 않으면 다음 날 실행은 옛 코드로 돈다.
예약 루프가 할 일을 마칠 때마다 여기서 확인하고, 아래를 모두 만족하면 SIGINT로 스스로 꺼진다.
그러면 런처(%LOCALAPPDATA%\\toolscout\\start_app.ps1)가 10초 뒤 새 코드로 다시 띄운다.

- 브랜치가 main이고, 추적 파일에 커밋 안 한 수정이 없고, HEAD가 앱이 뜰 때와 다르다 (작업 중인 기능 브랜치·반쯤 고친 파일은 안 올린다)
- 06:00~09:00 KST가 아니다 (검증·예열·하루 실행·첫 발송 시간대)
- 하루 실행·검증이 돌고 있지 않고, 재실행 예약이 없고, 다음 예정 작업까지 10분 넘게 남았다
git이 없으면(배포 컨테이너 등) 끈다. AUTO_RESTART=0이어도 끈다.
정상 종료가 FORCE_EXIT_SECONDS 안에 끝나지 않으면 강제 종료한다. 9/25 19:58 열린 MCP 연결 때문에 uvicorn이 "Shutting down"에서
멈춰 앱이 3분 꺼져 있었다(런처는 프로세스가 끝나야 다시 띄운다).
"""
import logging
import os
import signal
import subprocess
import threading
from datetime import datetime, time, timedelta
from pathlib import Path

log = logging.getLogger("toolscout.autorestart")

ROOT = Path(__file__).resolve().parent.parent
QUIET_FROM, QUIET_UNTIL = time(6, 0), time(9, 0)
EVENT_MARGIN = timedelta(minutes=10)
FORCE_EXIT_SECONDS = 20


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def repo_state() -> dict | None:
    """{"branch", "head", "dirty"}. git을 못 쓰면 None."""
    head = _git("rev-parse", "HEAD")
    if head is None:
        return None
    return {"branch": _git("branch", "--show-current") or "", "head": head,
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no"))}


class AutoRestart:
    def __init__(self, state_fn=repo_state, trigger=lambda: signal.raise_signal(signal.SIGINT),
                 force_exit=lambda: os._exit(3), force_after: float = FORCE_EXIT_SECONDS):
        self.state_fn, self.trigger, self.force_exit, self.force_after = state_fn, trigger, force_exit, force_after
        start = state_fn() if os.environ.get("AUTO_RESTART", "1") != "0" else None
        self.start_head = start["head"] if start else None
        self.fired = False

    def reason(self, now: datetime, busy: bool, next_event: datetime) -> str | None:
        """지금 재시작해야 하면 이유 한 줄, 아니면 None."""
        if self.start_head is None or self.fired or busy:
            return None
        if QUIET_FROM <= now.time() < QUIET_UNTIL or next_event - now <= EVENT_MARGIN:
            return None
        repo = self.state_fn()
        if not repo or repo["branch"] != "main" or repo["dirty"] or repo["head"] == self.start_head:
            return None
        return f"main이 {self.start_head[:7]} → {repo['head'][:7]}로 바뀜"

    def check(self, now: datetime, busy: bool, next_event: datetime) -> bool:
        why = self.reason(now, busy, next_event)
        if why is None:
            return False
        self.fired = True
        log.warning("코드가 바뀌어 앱을 재시작한다 (%s). 런처가 10초 뒤 다시 띄운다", why)
        timer = threading.Timer(self.force_after, self._force)  # 정상 종료가 멈추면 강제로 끝낸다
        timer.daemon = True
        timer.start()
        self.trigger()
        return True

    def _force(self) -> None:
        log.warning("정상 종료가 %s초 안에 끝나지 않아 강제 종료한다 (열린 연결 등). 런처가 10초 뒤 다시 띄운다", self.force_after)
        self.force_exit()
