"""E2B 연결 확인 (계획안 부록 D, 세션 8 1단계). 샌드박스 생성 → echo → 폐기, 단계별 시간.

실행: uv run python -m tests.e2b.smoke
- 기본 템플릿에 python3·node·npm·npx가 있는지도 본다 (probe_mcp 설치·실행 단계에 필요)
- 설치 뒤 외부 통신 차단(update_network deny_out)이 먹는지 본다 (부록 D ③ 도구 목록은 네트워크 차단)
E2B_API_KEY 값은 출력하지 않는다.
"""
import json
import sys
import time

import config  # noqa: F401  .env를 os.environ에 채운다

from e2b import Sandbox


def ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def main() -> int:
    report: dict = {"key": config.status(["E2B_API_KEY"])["E2B_API_KEY"]}
    total = time.perf_counter()
    started = time.perf_counter()
    sandbox = Sandbox.create(timeout=120)
    report["create_ms"] = ms(started)
    try:
        started = time.perf_counter()
        echo = sandbox.commands.run("echo toolscout-e2b-ok", timeout=30)
        report["echo_ms"] = ms(started)
        report["echo"] = echo.stdout.strip()
        versions = sandbox.commands.run("python3 --version; node --version; npm --version; npx --version", timeout=30)
        report["runtimes"] = versions.stdout.strip().splitlines()
        online = sandbox.commands.run("python3 -c \"import urllib.request;print(urllib.request.urlopen('https://registry.npmjs.org/', timeout=10).status)\"",
                                      timeout=30)
        report["network_before"] = online.stdout.strip()
        sandbox.update_network({"deny_out": ["0.0.0.0/0"]})
        blocked = sandbox.commands.run("python3 -c \"import urllib.request\ntry:\n urllib.request.urlopen('https://registry.npmjs.org/', timeout=8); print('열림')\n"
                                       "except Exception as e: print('차단', type(e).__name__)\"", timeout=30)
        report["network_after_deny"] = blocked.stdout.strip()
    finally:
        started = time.perf_counter()
        sandbox.kill()
        report["kill_ms"] = ms(started)
    report["total_ms"] = ms(total)
    checks = {
        "샌드박스_생성·echo·폐기": report.get("echo") == "toolscout-e2b-ok",
        "python3·node·npm_있음": len(report.get("runtimes", [])) == 4,
        "설치_단계_네트워크_열림": report.get("network_before") == "200",
        "차단_뒤_외부_통신_막힘": str(report.get("network_after_deny", "")).startswith("차단"),
    }
    report |= {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
