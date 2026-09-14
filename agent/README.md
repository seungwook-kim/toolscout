# agent/

에이전트 3개와 공통 판단 루프. 상태: `loop.py`, `tracing.py`, `curator.py`, `schemas.py` 구현 (계획안 5장, 9.3).

## 파일
- `loop.py`: `run(role, system_prompt, user_input, allowed_tools, max_steps)`. 모델 → 도구 요청 → MCP 실행 → 재호출. 토큰 합계·원문 반환
- `tracing.py`: Langfuse 스팬 래퍼. 키 없음·인증 실패면 로컬 JSONL 로그로 대체, trace_id는 항상 발급, `trace_url()`
- `curator.py`: 큐레이터. 20건 무작위 묶음 선별 → 사용자별 뉴스 5·도구 3(본 항목·가중치 -5 제외, 비움 이유) → 검증 요청 5
- `schemas.py`: 주제 10개(확정)와 선별·후보·검증 요청 출력 규격(pydantic). 검증 노드도 같은 규격을 쓴다
- `verifier.py`: 검증관. E2B 4단계, SKILL.md 판독 (예정)
- `explainer.py`: 해설가. 원문 재조회, 카드 JSON 작성 (예정)

## 들어오고 나가는 데이터
- 들어옴: `pipeline/`의 정리된 항목, 루트 `memory.py`의 사용자 기억, MCP 도구 결과(`<data>` 원문)
- 나감: 큐레이터 `{selected, plans, verify, stats, trace_id}`, 루프 이벤트(on_event, 나중에 SSE)

## 관련
- 루트 `models.py`·`providers.py`: 역할별 모델 호출 / 루트 `mcp_server.py`: 루프가 부르는 도구

## 할 일
- [ ] `explainer.py` (다음 단계)
- [ ] 큐레이터 기본 경로(Gemini 사고 minimal) 실제 검수. 오늘은 무료 한도 소진으로 대체 경로(nex-n2.5-mini 추론 끔)만 확인
- [ ] 선별 기준 편차: Gemini 34건, 대체 모델 94건. 무료 한도 초기화 후 같은 데이터로 비교
- [ ] Langfuse 스팬 전송 제한 시간(5초) 초과로 최상위 스팬이 빠진 트레이스 1건. 제한 시간 조정 여부 결정
- [ ] `verifier.py`와 되돌림 2개, 에이전트별 도구 호출 상한 (뼈대 완성 후)
