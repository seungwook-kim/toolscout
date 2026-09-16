"""E2B 샌드박스 안에서 돌리는 MCP 클라이언트 (계획안 부록 D ③). 표준 라이브러리만 쓴다 (샌드박스에 파일로 올려 실행).

stdio: python3 sandbox_probe.py --timeout 30 -- <서버 실행 명령과 인자...>
       서버를 띄워 initialize → notifications/initialized → tools/list (줄 단위 JSON-RPC)
http:  python3 sandbox_probe.py --timeout 30 --http <URL>
       엔드포인트 GET 응답 코드 + streamable HTTP로 initialize → tools/list (인증이 필요하면 401·403에서 멈춘다)
결과는 stdout에 JSON 한 줄:
  {"mode", "initialize": {protocolVersion, serverInfo} | null, "tools": [{name, description}], "error": 문자열 | null,
   "stderr_tail": 문자열, "exit_code": 정수 | null, "http_get_status": 정수 | null, "http_status": 정수 | null, "seconds": 실수}
"""
import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

PROTOCOL = "2025-06-18"
CLIENT = {"name": "toolscout-probe", "version": "0.1"}
TAIL = 2000


def _request(message_id, method, params=None):
    body = {"jsonrpc": "2.0", "id": message_id, "method": method}
    if params is not None:
        body["params"] = params
    return body


def _tools(result):
    return [{"name": t.get("name", ""), "description": (t.get("description") or "")[:200]} for t in result.get("tools", [])]


def probe_stdio(command, timeout):
    started = time.time()
    out = {"mode": "stdio", "initialize": None, "tools": [], "error": None, "stderr_tail": "", "exit_code": None,
           "http_get_status": None, "http_status": None}
    try:
        proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1)
    except OSError as exc:
        return out | {"error": f"실행 실패: {type(exc).__name__}: {exc}", "seconds": round(time.time() - started, 2)}
    lines, errors = queue.Queue(), []
    threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()
    threading.Thread(target=lambda: [errors.append(line) for line in proc.stderr], daemon=True).start()

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def wait_for(message_id):
        while time.time() - started < timeout:
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                if proc.poll() is not None and lines.empty():
                    raise RuntimeError(f"서버가 응답 전에 종료됨 (exit {proc.returncode})")
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue  # stdout에 로그를 섞는 서버
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"JSON-RPC 오류: {json.dumps(message['error'], ensure_ascii=False)[:300]}")
                return message.get("result") or {}
        raise TimeoutError(f"{timeout}초 안에 응답 없음")

    try:
        send(_request(1, "initialize", {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": CLIENT}))
        init = wait_for(1)
        out["initialize"] = {"protocolVersion": init.get("protocolVersion"), "serverInfo": init.get("serverInfo")}
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(_request(2, "tools/list", {}))
        out["tools"] = _tools(wait_for(2))
    except (OSError, RuntimeError, TimeoutError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        time.sleep(0.2)  # stderr 스레드가 마지막 줄을 받게
        out["exit_code"] = proc.returncode
        out["stderr_tail"] = "".join(errors)[-TAIL:]
    return out | {"seconds": round(time.time() - started, 2)}


def _post(url, message, session, timeout):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": PROTOCOL}
    if session:
        headers["Mcp-Session-Id"] = session
    request = urllib.request.Request(url, data=json.dumps(message).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
        session = response.headers.get("Mcp-Session-Id") or session
        status = response.status
    if not text.strip():
        return status, session, {}
    if text.lstrip().startswith("{"):
        return status, session, json.loads(text)
    for line in text.splitlines():  # text/event-stream: 마지막 data 줄의 JSON
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload.startswith("{"):
                data = json.loads(payload)
                if "id" in data:
                    return status, session, data
    return status, session, {}


def probe_http(url, timeout):
    started = time.time()
    out = {"mode": "http", "initialize": None, "tools": [], "error": None, "stderr_tail": "", "exit_code": None,
           "http_get_status": None, "http_status": None}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="GET", headers={"Accept": "text/event-stream"}),
                                    timeout=timeout) as response:
            out["http_get_status"] = response.status
    except urllib.error.HTTPError as exc:
        out["http_get_status"] = exc.code
    except (urllib.error.URLError, OSError) as exc:
        return out | {"error": f"엔드포인트 연결 실패: {type(exc).__name__}: {exc}", "seconds": round(time.time() - started, 2)}
    session = None
    try:
        status, session, init = _post(url, _request(1, "initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                                                     "clientInfo": CLIENT}), session, timeout)
        out["http_status"] = status
        if "error" in init:
            raise RuntimeError(f"JSON-RPC 오류: {json.dumps(init['error'], ensure_ascii=False)[:300]}")
        result = init.get("result") or {}
        out["initialize"] = {"protocolVersion": result.get("protocolVersion"), "serverInfo": result.get("serverInfo")}
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session, timeout)
        _, session, listed = _post(url, _request(2, "tools/list", {}), session, timeout)
        out["tools"] = _tools(listed.get("result") or {})
    except urllib.error.HTTPError as exc:
        out["http_status"] = exc.code
        out["error"] = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out | {"seconds": round(time.time() - started, 2)}


def main():
    parser = argparse.ArgumentParser(description="MCP initialize·tools/list 확인")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--http", default=None, help="원격 MCP 엔드포인트 URL")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- 뒤에 stdio 서버 실행 명령")
    args = parser.parse_args()
    command = [c for c in args.command if c != "--"] if args.command else []
    if args.http:
        result = probe_http(args.http, args.timeout)
    elif command:
        result = probe_stdio(command, args.timeout)
    else:
        result = {"mode": None, "error": "명령이나 --http가 필요함"}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
