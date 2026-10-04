"""MCP 실측 표시 검수 (2026-10-04, 10/2~10/4 발송분 점검). 가짜 샌드박스로 확인하고 E2B·모델·DB는 쓰지 않는다.

실행: uv run python -m tests.verify.check_probe_labels
사고: 도움말만 찍고 끝나는 CLI(llm-wiki-compiler·gflow-cli)와 키가 없어 못 띄운 서버(Memanto)가 카드에 "실행 실패"로 나갔고,
버전 업 MCP(anymd 8.3.0) 카드에 예전 버전(8.0.0) 실측이 붙었고, 웹 칩은 실패(bad)를 회색으로 그렸다.
- 도움말에 stdio MCP 하위 명령(serve·mcp)이 있으면 그 명령으로 1회 더 실행한다. HTTP 서버 하위 명령은 고르지 않는다
- 하위 명령이 없으면 실행·도구 목록·인증은 실패가 아니라 미확인, 도움말 낱말을 인증 요구로 보지 않는다
- 키가 필요해 실패한 단계는 카드에 "미확인(키 필요)" 경고, 원래 실패는 그대로 실패
- 레지스트리 버전과 실측 명령 버전이 다르면 발송 전 검증을 다시 한다
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from agent import probe
from pipeline import presend, verification

LLMWIKI_HELP = """Usage: llmwiki [options] [command]

Options:
  -V, --version                    output the version number

Commands:
  quickstart [options] <source>    Ingest a source and compile it into a wiki in one step. Token missing is fine.
  serve [options]                  Start an MCP server exposing wiki tools
"""
GFLOW_HELP = """Usage: gflow [OPTIONS] COMMAND [ARGS]...

Commands:
  run           Execute a JSON-described batch of image generations...
  serve         Start the gflow MCP server over HTTP.
"""
BARE_HELP = "Usage: tool [options]\n\nOptions:\n  --token TEXT  API token (missing means anonymous)\n"


class FakeSandbox:
    """설치는 늘 성공, 실행은 serve가 붙으면 살아 있고 아니면 도움말을 찍고 끝난다."""

    def __init__(self, help_text: str):
        self.help, self.commands_seen = help_text, []
        self.files = SimpleNamespace(write=lambda path, text: None)
        self.commands = SimpleNamespace(run=self.run)

    def run(self, command, timeout=None):
        self.commands_seen.append(command)
        served = " serve " in f"{command} "
        if command.startswith("ls /tmp/venv/bin"):
            out = "llmwiki\n"
        elif "timeout " in command and "EXIT=" in command:
            out = "EXIT=124" if served else "EXIT=1"
        elif command.startswith("tail -c"):
            out = "" if self.last_served else self.help
        elif "sandbox_probe.py" in command:
            ok = {"initialize": {"protocolVersion": "2025-06-18"}, "tools": [{"name": "search_wiki"}], "error": None}
            out = json.dumps(ok if served else {"initialize": None, "tools": [], "error": "RuntimeError: 서버가 응답 전에 종료됨"})
        else:
            out = ""
        if "timeout " in command:
            self.last_served = served
        return SimpleNamespace(exit_code=0, stdout=out, stderr="")

    last_served = False

    def update_network(self, rule):
        pass

    def kill(self):
        pass


def run_with(help_text: str) -> tuple[dict, FakeSandbox]:
    box = FakeSandbox(help_text)
    return probe.run("uvx llm-wiki-compiler@1.4.1", "pypi", sandbox_factory=lambda: box, auto=False), box


def row(run: str, tools_list: str, auth: str, requirements=()) -> SimpleNamespace:
    from datetime import datetime
    return SimpleNamespace(status="done", kind="pypi", install="성공", run=run, tools_list=tools_list, tools=[],
                           requirements=list(requirements), probed_at=datetime(2026, 10, 2, 22, 14),
                           stages={"install": {"ms": 18300}, "auth": {"status": auth}})


def main() -> int:
    served, box = run_with(LLMWIKI_HELP)
    bare, _ = run_with(BARE_HELP)
    keyed = verification.card_verification(row("실패", "실패", "필요", ["MOORCHEH_API_KEY"]))
    broken = verification.card_verification(row("실패", "실패", "미확인"))
    unsure = verification.card_verification(row("미확인", "미확인", "미확인"))
    item = {"install": {"packages": [{"registryType": "npm", "identifier": "@sylphx/anymd", "version": "8.3.0"}]}}
    checks = {
        "도움말의_stdio_MCP_하위명령": probe.mcp_subcommand(LLMWIKI_HELP) == "serve"
        and probe.mcp_subcommand("Usage: x\n\nCommands:\n  mcp    Run tools\n") == "mcp",
        "HTTP_서버_하위명령·도움말아님은_안고름": probe.mcp_subcommand(GFLOW_HELP) is None
        and probe.mcp_subcommand("  serve   Start an MCP server\n") is None,
        "하위명령으로_다시_실행·도구목록_성공": served["stages"]["run"]["status"] == "성공" and served["stages"]["tools_list"]["status"] == "성공"
        and served["command"] == "uvx llm-wiki-compiler@1.4.1 serve" and any("llmwiki serve" in c for c in box.commands_seen),
        "하위명령_없으면_미확인(실패_아님)": [bare["stages"][k]["status"] for k in ("run", "tools_list", "auth")] == ["미확인"] * 3
        and bare["requirements"] == [] and "도움말만" in bare["stages"]["run"]["note"],
        "키_필요_실패는_미확인(키_필요)_경고": (keyed["run"]["status"], keyed["run"]["label"]) == ("warn", "실행 미확인(키 필요)")
        and keyed["tools_list"]["label"] == "도구 목록 미확인(키 필요)" and keyed["auth_required"]["label"] == "MOORCHEH_API_KEY 필요",
        "원래_실패는_그대로_실패": (broken["run"]["status"], broken["run"]["label"]) == ("bad", "실행 실패"),
        "미확인은_회색_미확인": (unsure["run"]["status"], unsure["run"]["label"]) == ("na", "실행 미확인"),
        "버전_다르면_다시_실측": presend._stale(item, {"probe_command": "npx -y @sylphx/anymd@8.0.0"})
        and not presend._stale(item, {"probe_command": "npx -y @sylphx/anymd@8.3.0"})
        and not presend._stale(item, {"probe_command": None}) and not presend._stale({}, {"probe_command": "uvx a@1"}),
        "버전_일부만_같아도_다름(8.3.0≠8.3.01)": presend._stale(item, {"probe_command": "npx -y @sylphx/anymd@8.3.01"}),
        "웹_칩_실패는_빨강": 'bad: "bad"' in Path("web/cards.js").read_text(encoding="utf-8"),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
