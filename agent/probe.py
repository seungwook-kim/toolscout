"""probe_mcp 구현 (계획안 5장 도구 가드, 부록 D, 작업 규칙 조정: 설치 90초·실행 30초). E2B 샌드박스에서 MCP 동작 검증 4단계.

- 입력: 설치 명령(npx·npm install·uvx·pipx run·pip install), 종류(npm|pypi|remote), 원격이면 URL
- ① 설치: 네트워크 허용, 90초 ② 실행: 네트워크 차단 뒤 표준입력을 열어 둔 채 몇 초 살아 있는지, 30초.
  도움말만 찍고 끝나면 도움말의 MCP 하위 명령(serve·mcp 등)으로 1회 더, 없으면 실패가 아니라 미확인
  ③ 도구 목록: 네트워크 차단 상태에서 mcp/sandbox_probe.py로 initialize·tools/list ④ 인증 필요: 환경변수·토큰 요구 에러 패턴
- 원격 전용: ①② 해당없음, ③은 엔드포인트 GET 응답 + streamable HTTP initialize·tools/list, 401·403이면 ④ 인증 필요
- 가드: 명령에 curl·wget·sh -c·bash -c나 셸 메타문자가 있으면 샌드박스를 만들지 않고 거부. 자동 검증은 하루 30건
- 결과는 probes 표(item_id가 있을 때)에: 단계별 성공/실패/해당없음, duration_ms, requirements, tools, log 요약 2,000자
동작 검증이지 보안 검증이 아니다. 도구가 올바르게 동작하는지는 범위 밖이다.
"""
import json
import re
import shlex
import time
from datetime import datetime, time as dtime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

import db

INSTALL_TIMEOUT, RUN_TIMEOUT, TOOLS_TIMEOUT = 90, 30, 30
NODE_MAJOR, NODE_SETUP_TIMEOUT = "22", 40  # 샌드박스 기본 Node 20.9는 require(esm)을 못 해 멀쩡한 서버가 실행 실패로 나온다 (9/16 실측, n으로 약 6초)
ALIVE_SECONDS = 6  # 실행 단계: 이만큼 살아 있으면 기동 성공으로 본다 (stdio 서버는 입력을 기다리며 대기)
SANDBOX_LIFETIME = 300
DAILY_AUTO_LIMIT = 30
LOG_CHARS = 2000
OK, FAIL, NA, UNSURE = "성공", "실패", "해당없음", "미확인"
PROBE_SCRIPT = Path(__file__).resolve().parents[1] / "mcp" / "sandbox_probe.py"

FORBIDDEN = re.compile(r"curl|wget|\bsh\s+-c\b|\bbash\s+-c\b", re.I)
SHELL_META = re.compile(r"[;&|`$<>(){}\\\n]")
NPM_SPEC = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*(@[\w.^~*-]+)?$", re.I)
PYPI_SPEC = re.compile(r"^[A-Za-z0-9][\w.-]*(\[[\w,-]+\])?((==|>=|~=)[\w.*+-]+|@[\w.*+-]+)?$")
ARG = re.compile(r"^[\w@./:=,+%-]+$")
ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:API_KEY|KEY|TOKEN|SECRET|PASSWORD|PAT|CREDENTIALS?|ACCESS_KEY(?:_ID)?|URL|ID)\b")
AUTH_HINT = re.compile(r"api[ _-]?key|token|secret|credential|password|unauthori[sz]ed|authenticat|environment variable|env var"
                       r"|is required|must be (set|provided)|not (set|provided|found)|missing", re.I)
HELP = re.compile(r"^\s*(usage:|commands:|options:)", re.I | re.M)
SUBCOMMAND = re.compile(r"^\s{1,8}(mcp|stdio|serve|server)(?=\s|\[|$)([^\n]*)$", re.I | re.M)


class ProbeRejected(ValueError):
    pass


def parse_command(command: str, kind: str, url: str = "") -> dict:
    """설치 명령을 확인하고 나눈다. 반환: {kind, spec, args, url}. 가드에 걸리면 ProbeRejected."""
    kind = (kind or "").strip().lower()
    if kind == "remote":
        if "{" in (url or ""):
            raise ProbeRejected("실측 불가(자체 호스팅 주소): 주소에 자리표시자가 있음")
        if not re.match(r"^https://[\w.-]+(:\d+)?(/[\w./%~:@!,+=-]*)?(\?[\w./%~:@!,+=&-]*)?$", url or ""):
            raise ProbeRejected("원격 URL은 https 주소만 받는다")
        return {"kind": "remote", "spec": "", "args": [], "url": url}
    command = (command or "").strip()
    if FORBIDDEN.search(command):
        raise ProbeRejected("실측 불가(명령 형식): curl·wget·sh -c·bash -c가 들어 있음")
    if SHELL_META.search(command):
        raise ProbeRejected("실측 불가(명령 형식): 셸 메타문자가 들어 있음")
    tokens = command.split()
    if kind == "npm":
        if tokens[:1] == ["npx"]:
            rest = [t for t in tokens[1:] if t not in ("-y", "--yes")]
        elif tokens[:1] == ["npm"] and tokens[1:2] and tokens[1] in ("i", "install"):
            rest = [t for t in tokens[2:] if t not in ("-g", "--global")]
        else:
            raise ProbeRejected("npm은 'npx 패키지' 또는 'npm install 패키지' 형식만 받는다")
        pattern = NPM_SPEC
    elif kind == "pypi":
        if tokens[:1] == ["uvx"]:
            rest = tokens[1:]
        elif tokens[:2] == ["pipx", "run"]:
            rest = tokens[2:]
        elif tokens[:2] == ["pip", "install"] or tokens[:4] == ["python", "-m", "pip", "install"]:
            rest = tokens[2:] if tokens[0] == "pip" else tokens[4:]
        else:
            raise ProbeRejected("pypi는 'uvx 패키지', 'pipx run 패키지', 'pip install 패키지' 형식만 받는다")
        pattern = PYPI_SPEC
    else:
        raise ProbeRejected("종류는 npm, pypi, remote 중 하나")
    if not rest or not pattern.match(rest[0]):
        raise ProbeRejected("패키지 이름 형식이 올바르지 않음")
    if any(not ARG.match(a) for a in rest[1:]):
        raise ProbeRejected("실행 인자에 허용하지 않는 문자가 있음")
    return {"kind": kind, "spec": rest[0], "args": rest[1:], "url": ""}


def auth_requirements(*texts: str) -> tuple[list[str], bool]:
    """에러 문장에서 환경변수·토큰 요구를 찾는다. 반환: (요구 목록, 인증 힌트가 있었나)."""
    names, hinted = [], False
    for text in texts:
        for line in (text or "").splitlines():
            if not AUTH_HINT.search(line):
                continue
            hinted = True
            names += [n for n in ENV_NAME.findall(line) if n not in names]
    return names[:10], hinted


def today_count() -> int:
    start = datetime.combine(datetime.now(timezone.utc).date(), dtime.min)
    with db.get_engine().connect() as conn:
        return conn.execute(select(func.count()).select_from(db.Probe).where(db.Probe.probed_at >= start)).scalar() or 0


def _tail(text: str, n: int = 400) -> str:
    return (text or "").strip()[-n:]


def _run(sandbox, command: str, timeout: int) -> tuple[int, str, str]:
    """샌드박스 명령. 0이 아닌 종료도 예외 대신 (코드, stdout, stderr)로."""
    from e2b.sandbox.commands.command_handle import CommandExitException

    try:
        result = sandbox.commands.run(command, timeout=timeout)
        return result.exit_code, result.stdout, result.stderr
    except CommandExitException as exc:
        return exc.exit_code, exc.stdout, exc.stderr


def _install_npm(sandbox, spec: str) -> tuple[dict, list[str] | None]:
    started = time.perf_counter()
    node_code, _, _ = _run(sandbox, f"sudo npm install -g n --loglevel=error >/dev/null && sudo n {NODE_MAJOR} >/dev/null 2>&1", NODE_SETUP_TIMEOUT)
    runtime = f"node {NODE_MAJOR}" if node_code == 0 else "node 20(기본, 22 준비 실패)"
    code, out, err = _run(sandbox, "mkdir -p /tmp/probe && cd /tmp/probe && npm init -y >/dev/null && "
                                   f"npm install --no-audit --no-fund --loglevel=error {shlex.quote(spec)}", INSTALL_TIMEOUT)
    stage = {"status": OK if code == 0 else FAIL, "ms": int((time.perf_counter() - started) * 1000),
             "note": "" if code == 0 else _tail(err or out), "runtime": runtime}
    if code != 0:
        return stage, None
    name = re.sub(r"(?<!^)@[^/]*$", "", spec)  # 버전 떼기 (@scope는 남김)
    script = ("const p=require('/tmp/probe/node_modules/" + name + "/package.json');"
              "const b=p.bin;console.log(typeof b==='string'?(p.name.split('/').pop()):Object.keys(b||{}).join(' '))")
    _, bins, _ = _run(sandbox, f"node -e {shlex.quote(script)}", 20)
    names = bins.split()
    if not names:
        return stage | {"note": "설치됐지만 실행 파일(bin)이 없음"}, None
    short = name.split("/")[-1]
    chosen = next((b for b in names if b == short), next((b for b in names if short in b), names[0]))
    return stage, [f"/tmp/probe/node_modules/.bin/{chosen}"]


def _install_pypi(sandbox, spec: str) -> tuple[dict, list[str] | None]:
    started = time.perf_counter()
    pip_spec = spec.replace("@", "==", 1) if "@" in spec and "==" not in spec else spec
    code, out, err = _run(sandbox, "python3 -m venv /tmp/venv && ls /tmp/venv/bin > /tmp/bin_before && "
                                   f"/tmp/venv/bin/pip install --disable-pip-version-check -q {shlex.quote(pip_spec)}", INSTALL_TIMEOUT)
    stage = {"status": OK if code == 0 else FAIL, "ms": int((time.perf_counter() - started) * 1000),
             "note": "" if code == 0 else _tail(err or out)}
    if code != 0:
        return stage, None
    _, listing, _ = _run(sandbox, "ls /tmp/venv/bin | grep -vxF -f /tmp/bin_before", 20)
    names = [n for n in listing.split() if n and not n.startswith(("python", "pip", "activate"))]
    if not names:
        return stage | {"note": "설치됐지만 실행 파일이 없음"}, None
    base = re.split(r"[\[=@<>~]", spec)[0].lower().replace("_", "-")
    chosen = next((n for n in names if n.lower() == base), next((n for n in names if base in n.lower()), names[0]))
    return stage, [f"/tmp/venv/bin/{chosen}"]


def mcp_subcommand(help_text: str) -> str | None:
    """도움말이면 하위 명령 목록에서 stdio MCP 서버를 켜는 것. mcp·stdio는 이름만으로, serve·server는 설명에 MCP가 있을 때. HTTP·SSE는 뺀다."""
    found = SUBCOMMAND.finditer(help_text or "") if HELP.search(help_text or "") else ()
    return next((m.group(1) for m in found if not re.search(r"\b(HTTP|SSE)\b", m.group(2), re.I)
                 and (m.group(1).lower() in ("mcp", "stdio") or re.search(r"\bMCP\b", m.group(2), re.I))), None)


def _alive(sandbox, launch: list[str]) -> tuple[dict, str]:
    """② 실행: 표준입력을 열어 둔 채 ALIVE_SECONDS 살아 있으면 성공. 반환: (단계, 에러·출력 끝부분)."""
    quoted = " ".join(shlex.quote(p) for p in launch)
    t0 = time.perf_counter()
    code, out, _ = _run(sandbox, f"cd /tmp && (sleep {ALIVE_SECONDS + 4}) | timeout {ALIVE_SECONDS} {quoted} "
                                 ">/tmp/run.out 2>/tmp/run.err; echo EXIT=$?", RUN_TIMEOUT)
    exit_code = int(m.group(1)) if (m := re.search(r"EXIT=(\d+)", out or "")) else code
    _, run_err, _ = _run(sandbox, "tail -c 8000 /tmp/run.err; tail -c 8000 /tmp/run.out", 10)  # 긴 도움말도 머리(Usage)까지
    alive = exit_code == 124  # timeout이 끊었다 = 입력을 기다리며 살아 있었다
    return {"status": OK if alive else FAIL, "ms": int((time.perf_counter() - t0) * 1000),
            "note": "" if alive else f"종료 코드 {exit_code}: {_tail(run_err)}"}, run_err


def _probe_json(stdout: str) -> dict:
    for line in reversed((stdout or "").strip().splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    return {"error": "sandbox_probe 결과를 읽지 못함", "tools": [], "stderr_tail": _tail(stdout)}


def run(command: str = "", kind: str = "", url: str = "", item_id: int | None = None, *, auto: bool = True,
        sandbox_factory=None) -> dict:
    """4단계 검증. 반환: {status: done|incomplete|rejected, kind, stages{install,run,tools_list,auth}, tools, requirements,
    duration_ms, log, reason?}. sandbox_factory는 검수용 주입(기본 e2b.Sandbox.create)."""
    started = time.perf_counter()
    try:
        parsed = parse_command(command, kind, url)
    except ProbeRejected as exc:
        return {"status": "rejected", "kind": kind, "reason": str(exc), "stages": {}, "tools": [], "requirements": [],
                "duration_ms": 0, "log": str(exc)}
    if auto and item_id is not None and today_count() >= DAILY_AUTO_LIMIT:
        return {"status": "rejected", "kind": parsed["kind"], "reason": f"자동 검증 하루 {DAILY_AUTO_LIMIT}건 초과, 다음 날로 이월",
                "stages": {}, "tools": [], "requirements": [], "duration_ms": 0, "log": ""}
    if sandbox_factory is None:
        from e2b import Sandbox

        sandbox_factory = lambda: Sandbox.create(timeout=SANDBOX_LIFETIME)  # noqa: E731
    stages = {"install": {"status": NA}, "run": {"status": NA}, "tools_list": {"status": NA}, "auth": {"status": NA}}
    tools, requirements, notes = [], [], []
    try:
        sandbox = sandbox_factory()
    except Exception as exc:  # E2B 장애: 그날 실측은 미완료 (부록 D)
        return {"status": "incomplete", "kind": parsed["kind"], "reason": f"E2B 장애: {type(exc).__name__}", "stages": stages,
                "tools": [], "requirements": [], "duration_ms": int((time.perf_counter() - started) * 1000), "log": ""}
    status = "done"
    try:
        sandbox.files.write("/tmp/sandbox_probe.py", PROBE_SCRIPT.read_text(encoding="utf-8"))
        if parsed["kind"] == "remote":
            t0 = time.perf_counter()
            _, out, err = _run(sandbox, f"python3 /tmp/sandbox_probe.py --timeout {TOOLS_TIMEOUT} --http {shlex.quote(parsed['url'])}",
                               TOOLS_TIMEOUT * 3)
            result = _probe_json(out)
            tools = result.get("tools") or []
            ok = result.get("initialize") is not None and not result.get("error")
            http = [result.get("http_get_status"), result.get("http_status")]
            stages["tools_list"] = {"status": OK if ok else FAIL, "ms": int((time.perf_counter() - t0) * 1000), "count": len(tools),
                                    "endpoint": result.get("http_get_status"), "note": _tail(result.get("error") or err)}
            names, hinted = auth_requirements(result.get("error") or "")
            if 401 in http or 403 in http:
                requirements = names or ["Authorization 헤더(토큰)"]
                stages["auth"] = {"status": "필요", "requirements": requirements}
            elif ok:
                stages["auth"] = {"status": "불필요"}
            else:
                stages["auth"] = {"status": "미확인", "requirements": names} if hinted else {"status": NA}
                requirements = names
        else:
            install_stage, launch = (_install_npm if parsed["kind"] == "npm" else _install_pypi)(sandbox, parsed["spec"])
            stages["install"] = install_stage
            if launch:
                launch += parsed["args"]
                sandbox.update_network({"deny_out": ["0.0.0.0/0"]})  # 설치 단계만 네트워크 허용
                stages["run"], run_err = _alive(sandbox, launch)
                # 도움말만 찍고 끝나는 CLI는 MCP 서버를 켜는 하위 명령으로 한 번 더 (10/2 llm-wiki-compiler serve)
                if stages["run"]["status"] == FAIL and not parsed["args"] and (sub := mcp_subcommand(run_err)):
                    launch, command = launch + [sub], f"{command} {sub}"
                    stages["run"], run_err = _alive(sandbox, launch)
                if help_only := stages["run"]["status"] == FAIL and bool(HELP.search(run_err)):  # 못 띄워 본 것이지 고장이 아니다
                    stages["run"] |= {"status": UNSURE, "note": "도움말만 출력하고 끝남(MCP 서버 시작 명령을 찾지 못함)"}
                quoted = " ".join(shlex.quote(p) for p in launch)
                t0 = time.perf_counter()
                _, out, err = _run(sandbox, f"cd /tmp && python3 /tmp/sandbox_probe.py --timeout {TOOLS_TIMEOUT} -- {quoted}",
                                   TOOLS_TIMEOUT + 15)
                result = _probe_json(out)
                tools = result.get("tools") or []
                ok = result.get("initialize") is not None and not result.get("error")
                stages["tools_list"] = {"status": OK if ok else FAIL, "ms": int((time.perf_counter() - t0) * 1000), "count": len(tools),
                                        "note": _tail(result.get("error") or "")}
                requirements, hinted = auth_requirements(run_err, result.get("stderr_tail") or "", result.get("error") or "")
                if help_only and not ok:  # 도움말 문장의 "missing"·"token" 같은 낱말을 인증 요구로 보지 않는다
                    stages["tools_list"]["status"], stages["auth"], requirements = UNSURE, {"status": UNSURE}, []
                elif requirements or (hinted and not ok):
                    stages["auth"] = {"status": "필요", "requirements": requirements}
                elif ok:
                    stages["auth"] = {"status": "불필요"}
                else:
                    stages["auth"] = {"status": UNSURE}
            else:
                notes.append(install_stage.get("note", ""))
    except Exception as exc:  # 샌드박스 명령 시간 초과·연결 끊김: 미완료, 내일 재시도
        status = "incomplete"
        notes.append(f"{type(exc).__name__}: {str(exc)[:200]}")
    finally:
        try:
            sandbox.kill()
        except Exception:  # 폐기 실패는 샌드박스 수명(SANDBOX_LIFETIME)이 끝내 준다
            notes.append("샌드박스 폐기 요청 실패(수명 만료로 정리됨)")
    duration = int((time.perf_counter() - started) * 1000)
    labels = {"install": "① 설치", "run": "② 실행", "tools_list": "③ 도구 목록", "auth": "④ 인증"}
    lines = [f"{labels[k]} {v['status']}" + (f" {v['ms'] / 1000:.1f}s" if v.get("ms") else "") + (f" {v['note']}" if v.get("note") else "")
             for k, v in stages.items()]
    if tools:
        lines.append("도구: " + ", ".join(t["name"] for t in tools[:40]))
    log = "\n".join(lines + [n for n in notes if n])[:LOG_CHARS]
    outcome = {"status": status, "kind": parsed["kind"], "stages": stages, "tools": tools[:50], "requirements": requirements,
               "duration_ms": duration, "log": log, "command": command if parsed["kind"] != "remote" else parsed["url"]}
    if item_id is not None and status != "rejected":
        save(item_id, outcome)
    return outcome


def save(item_id: int, outcome: dict) -> None:
    stages = outcome["stages"]
    auth = stages.get("auth", {}).get("status")
    values = {"item_id": item_id, "install": stages["install"]["status"], "run": stages["run"]["status"],
              "tools_list": stages["tools_list"]["status"], "auth_required": True if auth == "필요" else False if auth == "불필요" else None,
              "duration_ms": outcome["duration_ms"], "requirements": outcome["requirements"], "log": outcome["log"],
              "probed_at": db.utcnow().replace(tzinfo=None), "status": outcome["status"], "kind": outcome["kind"],
              "command": outcome.get("command"), "tools": [t["name"] for t in outcome["tools"]], "stages": stages}
    statement = insert(db.Probe).values(values)
    statement = statement.on_conflict_do_update(index_elements=["item_id"], set_={k: statement.excluded[k] for k in values if k != "item_id"})
    with db.get_engine().begin() as conn:
        conn.execute(statement)
