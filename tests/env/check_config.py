"""config.py 검수 (작업 규칙 11). 값은 출력하지 않고 '설정됨/비어있음'만 표시한다.

실행: uv run python -m tests.env.check_config
"""
import io
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

import config

ROOT = Path(__file__).resolve().parents[2]
FAKE = "fake-secret-value-1234"  # 검사용 가짜 값. 로그에 나오면 실패


def parser_checks() -> dict:
    sample = "\n".join([
        f"GOOD_PLAIN={FAKE}",
        f"GOOD_QUOTED='{FAKE}'",
        f"GOOD_COMMENT={FAKE} # 설명",
        f"export GOOD_EXPORT={FAKE}",
        f"BAD_DUP=BAD_DUP={FAKE}",
        f"BAD_SPACE=abcd efgh {FAKE}",
        f"BAD_QUOTE=\"{FAKE}",
        "이건 형식이 아님",
    ])
    names = ["GOOD_PLAIN", "GOOD_QUOTED", "GOOD_COMMENT", "GOOD_EXPORT", "BAD_DUP", "BAD_SPACE", "BAD_QUOTE"]
    for name in names:
        os.environ.pop(name, None)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    config.log.addHandler(handler)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".env"
        path.write_text(sample, encoding="utf-8")
        problems = config.load(path)
    config.log.removeHandler(handler)
    logged = stream.getvalue()
    good = all(os.environ.get(n) == FAKE for n in names[:4])
    for name in names:
        os.environ.pop(name, None)
    return {
        "정상_줄_4종_해석": good,
        "깨진_줄은_키이름만": problems == ["BAD_DUP", "BAD_SPACE", "BAD_QUOTE", "8번째 줄"],
        "로그에_값_없음": FAKE not in logged and "abcd" not in logged,
        "기존_환경변수_안_덮어씀": _no_override(),
        "redact_가림": _redact_works(),
    }


def _no_override() -> bool:
    os.environ["KEEP_ME"] = "from-platform"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ".env"
        path.write_text("KEEP_ME=from-dotenv", encoding="utf-8")
        config.load(path)
    kept = os.environ.pop("KEEP_ME") == "from-platform"
    return kept


def _redact_works() -> bool:
    name = next((n for n in sorted(config._state["keys"]) if len(os.environ.get(n, "")) >= config.MIN_SECRET_LENGTH), None)
    if name is None:
        return True  # 가릴 값이 없으면 검사할 것도 없다
    return config.redact(f"error near {os.environ[name]} here") == "error near *** here"


def env_keys() -> list[str]:
    names = []
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            names.append(line.split("=", 1)[0].strip())
    return names


def main() -> int:
    checks = parser_checks()
    report = {
        "env_file": "있음" if config.ENV_PATH.exists() else "없음",
        "status": config.status(env_keys()),
        "problem_keys": config._state["problems"],
        "checks": checks,
        "pass": all(checks.values()),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
