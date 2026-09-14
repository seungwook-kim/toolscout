"""Langfuse 스팬 래퍼 (작업 규칙 10).

모든 LLM 호출과 도구 호출은 `span()` 안에서 한다. Langfuse 키가 없거나 인증이 실패하면
로컬 JSONL 로그로 대체하고, 어느 쪽이든 trace_id는 항상 돌려준다. 발송을 막지 않는다.
"""
import contextvars
import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import config  # noqa: F401  .env를 os.environ에 채운다

log = logging.getLogger("toolscout.tracing")

LOCAL_LOG = Path(os.environ.get("LOCAL_TRACE_LOG", "toolscout_trace.jsonl"))
LOCAL_MAX_CHARS = 500  # 로컬 로그에 기사 본문이 쌓이지 않게 자른다 (절대 규칙 9)

_current_trace: contextvars.ContextVar[str | None] = contextvars.ContextVar("toolscout_trace_id", default=None)
_state: dict[str, Any] = {"mode": None, "client": None}


def mode() -> str:
    """현재 기록 방식: "langfuse" 또는 "local"."""
    if _state["mode"] is None:
        _state["mode"], _state["client"] = _connect()
    return _state["mode"]


def _connect() -> tuple[str, Any]:
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        log.warning("Langfuse 키 없음, 로컬 로그로 대체: %s", LOCAL_LOG)
        return "local", None
    try:
        from langfuse import Langfuse

        client = Langfuse(timeout=5)
        if client.auth_check():
            return "langfuse", client
        log.warning("Langfuse 인증 실패, 로컬 로그로 대체")
    except Exception as exc:  # 관측 도구 장애가 서비스 장애가 되지 않게 전부 삼킨다
        log.warning("Langfuse 연결 실패(%s), 로컬 로그로 대체", type(exc).__name__)
    return "local", None


def current_trace_id() -> str | None:
    return _current_trace.get()


class Span:
    """Langfuse 관찰 객체와 로컬 기록을 같은 모양으로 다룬다."""

    def __init__(self, name: str, kind: str, trace_id: str, observation: Any = None):
        self.name, self.kind, self.trace_id = name, kind, trace_id
        self.fields: dict[str, Any] = {}
        self._observation = observation

    def update(self, **fields: Any) -> None:
        self.fields.update(fields)
        if self._observation is not None:
            try:
                self._observation.update(**fields)
            except Exception as exc:
                log.warning("Langfuse 스팬 갱신 실패(%s)", type(exc).__name__)


@contextmanager
def span(name: str, *, kind: str = "span", trace_id: str | None = None, **fields: Any) -> Iterator[Span]:
    """스팬 하나를 연다. kind는 Langfuse as_type(span, generation, tool, agent 등)."""
    parent_trace = _current_trace.get() or trace_id
    if mode() == "langfuse":
        client = _state["client"]
        options: dict[str, Any] = {"name": name, "as_type": kind, **fields}
        if parent_trace and _current_trace.get() is None:
            options["trace_context"] = {"trace_id": parent_trace}
        with client.start_as_current_observation(**options) as observation:
            token = _current_trace.set(observation.trace_id)
            current = Span(name, kind, observation.trace_id, observation)
            try:
                yield current
            except Exception as exc:
                current.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                _current_trace.reset(token)
        return

    current = Span(name, kind, parent_trace or uuid.uuid4().hex)
    current.fields.update(fields)
    token = _current_trace.set(current.trace_id)
    started = time.perf_counter()
    try:
        yield current
    except Exception as exc:
        current.fields.update(level="ERROR", status_message=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        _current_trace.reset(token)
        _write_local(current, (time.perf_counter() - started) * 1000)


def flush() -> None:
    if _state["client"] is not None:
        _state["client"].flush()


def _write_local(current: Span, duration_ms: float) -> None:
    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "trace_id": current.trace_id,
        "name": current.name,
        "kind": current.kind,
        "duration_ms": round(duration_ms, 1),
        **{key: _clip(value) for key, value in current.fields.items()},
    }
    try:
        with LOCAL_LOG.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError as exc:
        log.warning("로컬 트레이스 기록 실패(%s)", type(exc).__name__)


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= LOCAL_MAX_CHARS else text[:LOCAL_MAX_CHARS] + "…(잘림)"
