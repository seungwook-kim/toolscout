"""Claude 구독 공급자(claude_cli.py) 검수 (2026-09-28). 가짜 실행기로 확인하고 실제 claude CLI는 띄우지 않는다.

실행: uv run python -m tests.models.check_claude_cli
- 인자: -p·JSON 출력·모델·시스템 프롬프트 파일·Claude Code 도구 끔·safe-mode·strict MCP·세션 안 남김, 새 프로세스 그룹·숨은 창
- 환경: ANTHROPIC_API_KEY를 자식에게 넘기지 않는다(구독 대신 API 과금으로 바뀌지 않게)
- 답: result·토큰 수를 AIMessage로. 대화가 여러 턴이면 글로 이어 붙인다
- 실패: 한도·로그인은 529이고 30분 동안 CLI를 띄우지 않고 바로 넘김, 그 밖의 실패·시간 초과·CLI 없음·도구 요청은 503
"""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import claude_cli
import models


def fake_runner(record: dict, stdout: str = "", returncode: int = 0, stderr: str = "", raise_timeout: bool = False):
    def run(args, **kwargs):
        record.update(args=args, **{k: kwargs.get(k) for k in ("input", "env", "creationflags", "timeout")})
        record["system"] = open(args[args.index("--system-prompt-file") + 1], encoding="utf-8").read()
        if raise_timeout:
            raise subprocess.TimeoutExpired(args, kwargs.get("timeout"))
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
    return run


def status(fn) -> int | None:
    try:
        fn()
    except claude_cli.ClaudeCliError as exc:
        return exc.status_code
    return None


def main() -> int:
    claude_cli.executable = lambda: "claude"  # 설치 여부와 상관없이
    os.environ["ANTHROPIC_API_KEY"] = "검수용-가짜-키"
    os.environ["CLAUDE_CODE_SESSION_ID"] = "검수용"
    messages = [SystemMessage("너는 검수용이다"), HumanMessage("<data>안녕</data>")]
    ok = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": '{"ok": true}',
                     "usage": {"input_tokens": 12, "output_tokens": 5}, "total_cost_usd": 0.001, "stop_reason": "end_turn"})
    record: dict = {}
    answer = claude_cli.call("claude-sonnet-5", messages, None, runner=fake_runner(record, ok))
    args = record["args"]
    multi: dict = {}
    claude_cli.call("claude-haiku-4-5-20251001", messages + [AIMessage("{끊긴"), HumanMessage("형식이 틀렸다. 다시")], None,
                    runner=fake_runner(multi, ok))

    now = [1000.0]
    clock = lambda: now[0]  # noqa: E731
    calls: list = []
    limit_run = fake_runner({}, json.dumps({"is_error": True, "result": "Claude usage limit reached"}), returncode=1)
    counted = lambda *a, **k: calls.append(1) or limit_run(*a, **k)  # noqa: E731
    first = status(lambda: claude_cli.call("m", messages, None, runner=counted, clock=clock))
    second = status(lambda: claude_cli.call("m", messages, None, runner=counted, clock=clock))
    now[0] += claude_cli.BLOCK_SECONDS + 1
    third = status(lambda: claude_cli.call("m", messages, None, runner=counted, clock=clock))
    claude_cli._blocked_until["at"] = 0.0

    checks = {
        "인자_구독_한번묻기·도구끔·설정안불러옴": args[:3] == ["claude", "-p", "--output-format"] and args[args.index("--model") + 1] == "claude-sonnet-5"
        and args[args.index("--tools") + 1] == "" and all(f in args for f in ("--safe-mode", "--strict-mcp-config", "--no-session-persistence")),
        "시스템_프롬프트는_파일로_그대로": record["system"] == "너는 검수용이다",
        "새_프로세스그룹·숨은창(신호가_앱에_안닿게)": record["creationflags"] == claude_cli.NO_WINDOW and record["timeout"] == claude_cli.TIMEOUT,
        "API키·바깥세션변수를_자식에_안넘김": not any(k.startswith(("ANTHROPIC_", "CLAUDE")) for k in record["env"]),
        "한턴은_사용자글_그대로": record["input"] == "<data>안녕</data>",
        "여러턴은_글로_이어붙임": "[이전 답]\n{끊긴" in multi["input"] and "[사용자]\n형식이 틀렸다. 다시" in multi["input"],
        "답·토큰_읽기": answer.text == '{"ok": true}' and answer.usage_metadata["input_tokens"] == 12
        and answer.response_metadata["provider"] == "claude_code",
        "한도는_529·30분은_CLI_안띄움·지나면_다시": (first, second, third) == (529, 529, 529) and len(calls) == 2,
        "그밖의_실패는_503": status(lambda: claude_cli.call("m", messages, None, runner=fake_runner({}, "", 1, "boom"))) == 503,
        "시간초과는_503": status(lambda: claude_cli.call("m", messages, None, runner=fake_runner({}, raise_timeout=True))) == 503,
        "도구요청은_503(다음_제공자로)": status(lambda: claude_cli.call("m", messages, [{"type": "function"}])) == 503,
        "529·503은_models가_바로_전환": models.failover_reason(claude_cli.ClaudeCliError("x", 529)) == "529"
        and models.failover_reason(claude_cli.ClaudeCliError("x", 503)) == "503",
    }
    os.environ.pop("ANTHROPIC_API_KEY", None)
    claude_cli.executable = lambda: None
    checks["CLI_없으면_503"] = status(lambda: claude_cli.call("m", messages, None)) == 503
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
