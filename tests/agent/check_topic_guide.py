"""주제 경계 검수 (2026-09-23). 선별 프롬프트에 주제별 정의가 빠짐없이 들어가는지 본다. 모델·네트워크를 쓰지 않는다.

실행: uv run python -m tests.agent.check_topic_guide
- 주제 10개 모두 TOPIC_GUIDE가 있고 비어 있지 않다. 주제 목록에 없는 정의가 없다
- SELECT_PROMPT에 주제마다 "id: 이름. 정의" 한 줄이 들어간다
- 단어가 아니라 글이 다루는 것으로 정한다는 규칙과, 개발 주제 셋(agent_framework·mcp_tools·coding_tools)의 경계 규칙이 있다
- 선별 프롬프트가 1,800자 이내 (로컬 모델 문맥 8192토큰 여유, 실측은 아래 주석)
효과 측정(같은 9/23 뉴스 193건, 선별 통과 약 120건을 사람이 매긴 주제와 비교, gemma3:12b): 정확 56% → 70%.
측정 방법과 숫자는 agent/CHANGELOG.md 2026-09-23 항목.
"""
import json
import sys

from agent import curator, schemas

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


check("주제 10개 모두 정의가 있음", set(schemas.TOPIC_GUIDE) == set(schemas.TOPICS) and all(v.strip() for v in schemas.TOPIC_GUIDE.values()))
check("프롬프트에 주제마다 이름과 정의", all(f"{k}: {schemas.TOPICS[k]}. {schemas.TOPIC_GUIDE[k]}" in curator.SELECT_PROMPT for k in schemas.TOPICS))
check("단어가 아니라 다루는 것으로 정한다는 규칙", "제목에 나온 단어가 아니라" in curator.SELECT_PROMPT)
check("개발 주제 셋의 경계 규칙", "agent_framework·mcp_tools·coding_tools는 개발 방법·도구 자체를 다룰 때만" in curator.SELECT_PROMPT)
check("model_release는 기존 모델 사용 사례를 뺀다", "이미 나온 모델을 쓴" in schemas.TOPIC_GUIDE["model_release"])
# 2026-09-23 Ollama 실측(gemma3:12b): 이 프롬프트 749토큰, 프롬프트+실제 20건 묶음 최대 3,226토큰(전 2,845). 답 약 1,500토큰을 더해도 8,192 안.
# 프롬프트가 크게 늘어 이 여유를 먹지 않게 글자 수로 막는다 (지금 1,457자)
check(f"선별 프롬프트 1,800자 이내 (지금 {len(curator.SELECT_PROMPT)}자)", len(curator.SELECT_PROMPT) <= 1800)

passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
