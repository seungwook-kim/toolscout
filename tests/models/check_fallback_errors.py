"""제공자 전환 중 오류 검수 (2026-09-28 07:19 사고). 모델·네트워크·DB를 쓰지 않는다.

실행: uv run python -m tests.models.check_fallback_errors
사고: 검증관이 Groq로 README를 읽은(도구 호출) 뒤 429로 Gemini에 넘어가자, Gemini 3가 서명(thought_signature) 없는 도구 호출 기록을
400 INVALID_ARGUMENT로 거절했고, 그 오류가 검증 연결 전체를 끊었다(발송 전 검증 anythingmcp 새 버전 카드).
- providers.gemini_contents: 다른 제공자의 도구 호출·결과는 글로 바뀌고(함수 호출 부분 없음), Gemini가 만든 호출은 원본 parts 그대로
- verifier.run: 한 건이 예상 못 한 오류를 내도 그 건만 미완료(다음 날 재시도)이고 다음 건은 계속한다
"""
import asyncio
import json
import sys

from google.genai import types
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import providers
from agent import verifier
from pipeline import verification


def conversion() -> dict:
    native = [types.Part(function_call=types.FunctionCall(name="fetch_article", args={"url": "https://b.test"}, id="g1"),
                         thought_signature=b"sig")]
    history = [HumanMessage("<data>item</data>"),
               AIMessage("", tool_calls=[{"name": "fetch_article", "args": {"url": "https://a.test"}, "id": "groq1", "type": "tool_call"}]),
               ToolMessage("README 내용", tool_call_id="groq1", name="fetch_article"),
               AIMessage("", tool_calls=[{"name": "fetch_article", "args": {"url": "https://b.test"}, "id": "g1", "type": "tool_call"}],
                         additional_kwargs={"gemini_parts": native}),
               ToolMessage("두 번째 결과", tool_call_id="g1", name="fetch_article")]
    contents = providers.gemini_contents(history)
    foreign = contents[1:3]
    return {
        "다른제공자_호출은_글로": all(not p.function_call and not p.function_response for c in foreign for p in c.parts)
        and "[도구 호출 fetch_article]" in foreign[0].parts[0].text and "https://a.test" in foreign[0].parts[0].text,
        "다른제공자_결과도_글로·내용유지": foreign[1].role == "user" and foreign[1].parts[0].text == "[도구 결과 fetch_article] README 내용",
        "Gemini_호출은_원본(서명)그대로": contents[3].parts[0].function_call.id == "g1" and contents[3].parts[0].thought_signature == b"sig",
        "Gemini_결과는_함수응답": contents[4].parts[0].function_response is not None and contents[4].parts[0].function_response.id == "g1",
        "역할_순서": [c.role for c in contents] == ["user", "model", "user", "model", "user"],
    }


def continue_after_error() -> dict:
    marked, before = [], (verifier._verify_mcp, verification.mark)

    async def fake(request, call_tool, stats, model_call, mcp_url):
        if request["item_id"] == 1:
            raise RuntimeError("ClientError 400 INVALID_ARGUMENT")  # 제공자 400처럼 전환 대상이 아닌 오류
        return {"status": "done", "reason": None, "tool_calls": 1}

    verifier._verify_mcp = fake
    verification.mark = lambda item_id, status, error=None: marked.append((item_id, status, error))
    try:
        requests = [{"item_id": n, "kind": "mcp", "title": f"t{n}", "url": f"https://x.test/{n}"} for n in (1, 2)]
        result = asyncio.run(verifier.run(requests, call_tool=lambda name, args: None))
    finally:
        verifier._verify_mcp, verification.mark = before
    return {
        "오류난_건은_미완료·이유": marked[0][:2] == (1, "incomplete") and "RuntimeError" in (marked[0][2] or ""),
        "다음_건은_계속": marked[1][:2] == (2, "done") and result["counts"] == {"incomplete": 1, "done": 1},
    }


def main() -> int:
    checks = conversion() | continue_after_error()
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
