"""에이전트 공통: 모델에게 JSON 규격 응답을 받는다 (큐레이터·해설가).

agent/schemas.py 규격으로 검사하고, 틀리면 오류를 알려 1회 다시 부른다. 그래도 틀리면 실패 예시를 남기고 None.
모든 호출은 온도 0이다 (계획안 10장 출력 품질). 모델 장애(models.ModelUnavailable)는 호출부가 단위별로 처리한다.
"""
import json
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

import models
from agent import loop

MAX_EXAMPLES = 3  # 보고에 보여 줄 개수. 예시는 모두 모으고 하루 실행이 파일에 쌓는다


@dataclass
class Stats:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    format_failures: int = 0  # 규격에 안 맞은 응답 수 (재시도로 잡힌 것 포함)
    unrecovered: int = 0  # 재시도 후에도 안 맞은 요청 수
    failure_examples: list[dict] = field(default_factory=list)
    model_failures: list[dict] = field(default_factory=list)  # 제공자를 끝까지 시도해도 실패한 단위 {label, reason}

    def model_failed(self, label: str, exc: models.ModelUnavailable) -> str:
        reason = f"모델 장애 ({'; '.join(exc.attempts)})"[:300]
        self.model_failures.append({"label": label, "reason": reason})
        return reason


async def ask_json(role: str, prompt: str, payload: Any, schema: type[BaseModel], stats: Stats,
                   check: Callable[[Any], None] | None = None, label: str = "",
                   model_call: Callable[..., Any] | None = None) -> Any:
    """반환: 규격 객체 또는 None. check는 규격 밖 조건(id 범위 등)을 검사하고 틀리면 ValueError를 낸다."""
    call = model_call or partial(models.call, temperature=0)
    error = None
    for attempt in (1, 2):
        system = prompt if error is None else f"{prompt}\n\n직전 출력이 규격에 맞지 않았다 ({error}). 규격대로 다시 출력한다."
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        result = await loop.run(role, system, text, [], 1, model_call=call)
        stats.calls += 1
        stats.input_tokens += result["usage"]["input_tokens"]
        stats.output_tokens += result["usage"]["output_tokens"]
        try:
            if not isinstance(result["output"], dict) or set(result["output"]) == {"text"}:
                # parse_output이 JSON을 못 읽으면 {"text": 원문}을 준다. 기본값만 있는 규격(빈 목록)으로 통과되지 않게 막는다
                raise ValueError("JSON 객체가 아니다 (출력이 끊겼거나 형식이 틀림)")
            parsed = schema.model_validate(result["output"])
            if check:
                check(parsed)
            return parsed
        except (ValidationError, ValueError) as exc:
            stats.format_failures += 1
            error = _error_text(exc)
            stats.failure_examples.append({"label": label, "attempt": attempt, "error": error,
                                           "provider": result.get("provider"), "model": result.get("model"),
                                           "raw_head": (result.get("raw") or "")[:300],
                                           "raw_tail": (result.get("raw") or "")[-150:], "trace_id": result["trace_id"]})
    stats.unrecovered += 1
    return None


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or '전체'}: {e['msg']}" for e in exc.errors()[:3])[:300]
    return str(exc)[:300]
