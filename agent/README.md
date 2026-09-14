# agent/

에이전트 3개와 공통 판단 루프. 상태: `loop.py`, `tracing.py` 구현 (계획안 5장, 9.3).

## 파일
- `loop.py`: `run(role, system_prompt, user_input, allowed_tools, max_steps)`. 모델 → 도구 요청 → MCP 실행 → 재호출. DEV_MODE면 안내 로그 1회
- `tracing.py`: Langfuse 스팬 래퍼. 키 없음·인증 실패면 로컬 JSONL 로그로 대체, trace_id는 항상 발급, `trace_url()`
- `curator.py`: 큐레이터. 선별, 사용자별 정렬, 검증 요청, 비움 판단 (예정)
- `verifier.py`: 검증관. E2B 4단계, SKILL.md 판독 (예정)
- `explainer.py`: 해설가. 원문 재조회, 카드 JSON 작성 (예정)

## 들어오고 나가는 데이터
- 들어옴: `pipeline/`의 정리된 항목, MCP 도구 결과(`<data>`로 감싼 원문)
- 나감: `{status, output, steps, trace_id, tool_calls}`, 루프 이벤트(on_event, 나중에 SSE)

## 관련
- 루트 `models.py`: 역할별 모델 호출 / 루트 `mcp_server.py`: 루프가 부르는 도구

## 할 일
- [ ] OpenRouter 키 재발급 후 개발 모델로 "안녕"·도구 1개 실제 실행 (`tests/agent/run_loop.py`)
- [ ] `curator.py`, `explainer.py` (다음 세션 시작점: 큐레이터)
- [ ] `verifier.py`와 되돌림 2개 (뼈대 완성 후)
- [ ] 에이전트별 도구 호출 상한(계획안 5장 도구 가드) 반영
