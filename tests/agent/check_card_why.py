"""카드 "이 카드인 이유"를 데이터 근거로 만드는지 검수 (2026-09-27). 가짜 모델로 확인한다. 네트워크·DB를 쓰지 않는다.

실행: uv run python -m tests.agent.check_card_why
- 가중치가 양수인 관심 주제와 제목·설명에 단어로 나온 쓰는 도구만 근거로 쓴다 (다른 단어의 일부는 제외)
- 근거가 없으면 모델 이유, 그것도 없으면(되돌림 교체) 주제 이름. 120자 상한
- pick_for_user는 모델 이유를 pick_why로 옮기고 카드 이유를 근거로 바꾼다
왜: 9/16~9/27 메일에서 "관심 있는 개발자에게 유용한 도구입니다" 같은 되풀이 문장, "AIHawk 설치 실패 후 … 대체합니다" 같은 내부 사정이 나갔다.
9/27 실제 카드 8장에 적용하면 전부 근거 문장("관심 주제 'MCP·도구 연동' 관심도 3 · 쓰는 도구 mcp 관련" 등)이 되고 교체 사정은 사라진다.
"""
import asyncio
import json
import sys

from langchain_core.messages import AIMessage

from agent import card_why, curator
from agent.structured import Stats

MEMORY = {"user_id": 1, "is_test": True, "profile": {"role": "개발자", "tools_tags": ["python", "claude code", "mcp"]},
          "weights": {"model_release": 5, "mcp_tools": 3, "industry": 0, "pricing": -2}, "seen_urls": []}


def item(title: str, topic: str, summary: str = "") -> dict:
    return {"type": "skill", "title": title, "url": f"https://example.test/{abs(hash(title))}", "topic": topic, "summary": summary,
            "reason": "r", "source": "skillsmp"}


def main() -> int:
    build = lambda i, why="모델 이유": card_why.build(i, MEMORY, why)  # noqa: E731
    sent: list[str] = []

    def call(role, messages, tools=None):
        sent.append(messages[0].content)
        return AIMessage('{"news": [], "tools": [{"id": 1, "why": "MCP 연동에 관심 있는 개발자에게 유용한 도구입니다."}], "empty_reason": null}')

    plan = asyncio.run(curator.pick_for_user([item("vantadb-mcp", "mcp_tools", "MCP memory server")], MEMORY, Stats(), call))
    picked = plan["tools"][0]
    checks = {
        "관심주제_양수면_주제·관심도": build(item("새 모델", "model_release")) == "관심 주제 '모델 출시·성능' 관심도 5",
        "쓰는도구가_단어로_나오면_함께": build(item("vantadb-mcp", "mcp_tools", "Claude Code memory")) == (
            "관심 주제 'MCP·도구 연동' 관심도 3 · 쓰는 도구 claude code, mcp 관련"),
        "다른_단어의_일부는_도구로_안봄": card_why.tools_mentioned(item("pythonic mcpx", "industry"), ["python", "mcp"]) == [],
        "가중치_0·음수는_근거_아님": build(item("가격 소식", "pricing")) == "모델 이유" and build(item("투자 소식", "industry")) == "모델 이유",
        "근거·모델이유_없으면_주제이름": card_why.build(item("x", "industry"), MEMORY, None) == "오늘 선별된 '산업·투자·기업 동향' 항목",
        "120자_상한": len(build(item("x", "industry"), "가" * 300)) == card_why.MAX_CHARS,
        "pick_for_user_카드이유는_근거·모델이유는_pick_why": picked["why"] == "관심 주제 'MCP·도구 연동' 관심도 3 · 쓰는 도구 mcp 관련"
        and picked["pick_why"].startswith("MCP 연동에 관심 있는"),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
