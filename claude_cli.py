"""Claude 구독(Claude Code CLI)으로 모델을 부르는 공급자 (2026-09-28 사용자 결정 "지금은 너 자체의 구독 시스템으로 돌려라").

API 키 과금이 아니라 개발자 본인이 로그인해 둔 Claude Code(`claude -p`)를 한 번씩 실행해 답을 받는다.
- 우리 시스템 프롬프트만 쓴다(--system-prompt-file). Claude Code 자체 도구는 끄고(--tools ""), 이 PC의 CLAUDE.md·스킬·MCP·훅은
  불러오지 않는다(--safe-mode, --strict-mcp-config). 세션은 남기지 않는다(--no-session-persistence)
- 도구 호출은 지원하지 않는다(모델표 tools False). 도구가 필요한 호출(검증관 설치법 판단·질문 답)은 models.call이 다음 제공자로 넘긴다
- 사용 한도·로그인 문제는 529, 그 밖의 실패·시간 초과는 503으로 올려 models.call이 바로 다음 제공자(무료 모델)로 넘어가게 한다.
  429로 올리면 models.call이 60초 기다렸다 다시 부르는데, 구독 한도는 몇 시간씩 가서 호출마다 60초를 버린다.
  한도에 한 번 걸리면 BLOCK_SECONDS 동안은 CLI를 띄우지 않고 바로 넘긴다
- ANTHROPIC_* (API 키가 있으면 CLI가 API 과금으로 바뀐다)와 CLAUDE* (바깥 Claude Code 세션 표시)는 자식 프로세스 환경에서 뺀다
- 9/27 23:57 앱 런처가 Ctrl+C 이벤트로 죽은 적이 있어, CLI는 새 프로세스 그룹·숨은 창으로 띄워 그쪽 신호가 앱에 닿지 않게 한다
구독 요금제는 개인 사용 범위다. 다른 사용자를 받는 운영에서는 API 키(모델표 운영 모드)로 바꾼다.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

TIMEOUT = 240  # 해설가 원문 포함 한 번의 답. 넘으면 503으로 다음 제공자
BLOCK_SECONDS = 30 * 60
LIMIT_STATUS, FAIL_STATUS = 529, 503
_blocked_until = {"at": 0.0}
LIMIT_WORDS = re.compile(r"usage limit|rate limit|limit reached|too many requests|overloaded|not logged in|login|authenticat", re.I)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class ClaudeCliError(Exception):
    """status_code 529(한도·로그인) 또는 503(그 밖). models.failover_reason이 다음 제공자로 넘긴다. 사용자 글은 담지 않는다."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def executable() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude.exe"
    return str(fallback) if fallback.exists() else None


def transcript(conversation: list[BaseMessage]) -> str:
    """시스템 프롬프트를 뺀 대화를 한 덩어리 글로. 형식 재시도(직전 답 + 고쳐 달라는 요청)도 순서대로 담긴다."""
    if len(conversation) == 1 and isinstance(conversation[0], HumanMessage):
        return conversation[0].text
    parts = []
    for m in conversation:
        if isinstance(m, HumanMessage):
            parts.append(f"[사용자]\n{m.text}")
        elif isinstance(m, AIMessage):
            parts.append(f"[이전 답]\n{m.text}")
        elif isinstance(m, ToolMessage):
            parts.append(f"[도구 결과 {m.name or 'tool'}]\n{m.text}")
    return "\n\n".join(parts) + "\n\n위 대화에 이어 지금 답만 쓴다."


def call(model: str, messages: list[BaseMessage], tools, runner=subprocess.run, clock=time.monotonic) -> AIMessage:
    if tools:
        raise ClaudeCliError("claude_code는 도구 호출을 지원하지 않는다", FAIL_STATUS)
    if clock() < _blocked_until["at"]:
        raise ClaudeCliError("claude 구독 한도로 잠시 건너뜀", LIMIT_STATUS)
    exe = executable()
    if not exe:
        raise ClaudeCliError("claude CLI가 없다", FAIL_STATUS)
    system = "\n\n".join(m.text for m in messages if isinstance(m, SystemMessage))
    conversation = [m for m in messages if not isinstance(m, SystemMessage)]
    # API 키(과금 전환)와 바깥 Claude Code 세션 변수(CLAUDECODE·CLAUDE_CODE_* 등)는 넘기지 않는다. 앱은 작업 스케줄러에서 돌아
    # 그런 변수가 없고, 인증은 사용자 폴더의 로그인 정보로 한다
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "CLAUDE"))}
    with tempfile.TemporaryDirectory(prefix="toolscout_cc_") as work:
        system_file = Path(work) / "system.txt"
        system_file.write_text(system, encoding="utf-8")
        args = [exe, "-p", "--output-format", "json", "--model", model, "--system-prompt-file", str(system_file),
                "--tools", "", "--safe-mode", "--strict-mcp-config", "--no-session-persistence"]
        try:
            done = runner(args, input=transcript(conversation), capture_output=True, text=True, encoding="utf-8",
                          timeout=TIMEOUT, cwd=work, env=env, creationflags=NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCliError(f"claude CLI {TIMEOUT}초 초과", FAIL_STATUS) from exc
    try:
        data = json.loads(done.stdout or "{}")
    except json.JSONDecodeError:
        data = {}
    if done.returncode != 0 or data.get("is_error") or data.get("subtype", "success") != "success":
        detail = f"{data.get('result') or ''} {done.stderr or ''}"[:300]
        limited = bool(LIMIT_WORDS.search(detail))
        if limited:
            _blocked_until["at"] = clock() + BLOCK_SECONDS
        raise ClaudeCliError(f"claude CLI 실패(코드 {done.returncode}): {detail.strip()[:200]}", LIMIT_STATUS if limited else FAIL_STATUS)
    usage = data.get("usage") or {}
    return AIMessage(
        content=data.get("result") or "",
        usage_metadata={"input_tokens": int(usage.get("input_tokens") or 0), "output_tokens": int(usage.get("output_tokens") or 0),
                        "total_tokens": int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)},
        response_metadata={"provider": "claude_code", "model": model, "finish_reason": data.get("stop_reason"),
                           "api_equivalent_cost_usd": data.get("total_cost_usd")},
    )
