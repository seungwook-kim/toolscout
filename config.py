"""환경변수 로더 (작업 규칙 8·11). python-dotenv 없이 루트 .env를 os.environ에 채운다.

- 코드는 os.environ만 읽는다. 이 모듈은 import될 때 한 번 .env를 읽는다
- 이미 있는 환경변수는 덮어쓰지 않는다 (운영에서는 플랫폼 변수가 이긴다)
- 값은 어디에도 출력하지 않는다. 깨진 줄은 키 이름(키가 없으면 줄 번호)만 경고한다
"""
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("toolscout.config")

ENV_PATH = Path(__file__).resolve().parent / ".env"
KEY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MIN_SECRET_LENGTH = 6  # 이보다 짧은 값(예: 1, 10)은 가릴 필요가 없다

_state: dict = {"loaded": False, "keys": set(), "problems": []}


def load(path: Path = ENV_PATH) -> list[str]:
    """.env를 읽어 os.environ에 채운다. 반환: 문제가 있는 키 이름(또는 줄 번호) 목록."""
    if _state["loaded"] and path == ENV_PATH:
        return _state["problems"]
    problems: list[str] = []
    if path.exists():
        for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            name, sep, value = line.partition("=")
            name = name.strip()
            if not sep or not KEY_NAME.match(name):
                problems.append(f"{number}번째 줄")
                log.warning(".env %d번째 줄 형식이 깨짐 (값은 출력하지 않음)", number)
                continue
            parsed, reason = parse_value(name, value.strip())
            if reason:
                problems.append(name)
                log.warning(".env %s: %s (값은 출력하지 않음)", name, reason)
                continue
            _state["keys"].add(name)
            os.environ.setdefault(name, parsed)
    if path == ENV_PATH:
        _state.update(loaded=True, problems=problems)
    return problems


def parse_value(name: str, value: str) -> tuple[str, str | None]:
    """값을 해석한다. 반환: (값, 문제 설명 또는 None)."""
    if value.startswith(f"{name}="):
        return "", "값 안에 키 이름이 한 번 더 들어 있음"
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end == -1:
            return "", "따옴표가 닫히지 않음"
        return value[1:end], None
    value = value.split(" #", 1)[0].strip()  # 따옴표 없는 값 뒤의 주석
    if re.search(r"\s", value):
        return "", "따옴표 없이 공백이 들어 있음"
    return value, None


def status(names: list[str]) -> dict[str, str]:
    """키마다 '설정됨' 또는 '비어있음'만 돌려준다."""
    return {name: "설정됨" if os.environ.get(name, "").strip() else "비어있음" for name in names}


def redact(text: str) -> str:
    """오류 문구 등에 섞인 .env 값을 ***로 가린다."""
    for name in _state["keys"]:
        value = os.environ.get(name, "")
        if len(value) >= MIN_SECRET_LENGTH:
            text = text.replace(value, "***")
    return text


load()
