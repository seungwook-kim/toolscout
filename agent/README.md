# agent/

에이전트 3개와 공통 판단 루프. 상태: 만들 예정 (계획안 5장, 9.3).

## 파일
- `loop.py`: 직접 짠 루프. 모델 호출 → 도구 요청 파싱 → MCP 클라이언트 실행 → 재호출, 상한, 스팬 (예정)
- `curator.py`: 큐레이터. 선별, 사용자별 정렬, 검증 요청, 비움 판단 (예정)
- `verifier.py`: 검증관. E2B 4단계, SKILL.md 판독 (예정)
- `explainer.py`: 해설가. 원문 재조회, 카드 JSON 작성 (예정)
- `tracing.py`: Langfuse 스팬 래퍼. 키 없음·인증 실패면 로컬 JSONL 로그로 대체, trace_id는 항상 발급

## 들어오는 데이터
- `pipeline/`에서 정규화·중복 제거된 항목
- `get_user_memory` 도구로 읽는 사용자 기억

## 나가는 데이터
- 카드 JSON (계획안 9.3 응답 규격), 검증 결과 JSON
- 루프 이벤트 (나중에 `events.py`가 SSE로 전송)

## 관련
- 루트 `models.py`: 역할별 모델 호출
- 루트 `mcp_server.py`: 에이전트가 쓰는 도구
