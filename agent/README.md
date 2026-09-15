# agent/

에이전트 3개와 공통 판단 루프. 상태: 검증관 빼고 구현 (계획안 5장, 9.3).

## 파일
- `loop.py`: `run(role, system_prompt, user_input, allowed_tools, max_steps)`. 모델 → 도구 요청 → MCP 실행 → 재호출. 토큰 합계·원문 반환
- `tracing.py`: Langfuse 스팬 래퍼. 키 없음·인증 실패면 로컬 JSONL 로그로 대체, trace_id는 항상 발급, `trace_url()`
- `structured.py`: JSON 규격 응답 받기. 온도 0, pydantic 검사, 형식 실패면 1회 재시도, 실패 예시(제공자·모델 포함)와 모델 장애 기록
- `curator.py`: 큐레이터. 20건 무작위 묶음 선별 → 사용자별 뉴스 5·도구 3(본 항목·가중치 -5 제외, 비움 이유) → 검증 요청 5. 모델 장애는 묶음·사용자 단위로 건너뜀
- `explainer.py`: 해설가. 항목마다 fetch_article 1회 + 모델 1회로 초안 카드. 관련도(relevance) 3 미만·프로필과 안 이어지면 반려, 못 읽으면 "원문 확인 필요"
- `glossary.md`: 해설가 용어집 30개와 표기 원칙. 프롬프트에 그대로 붙는다
- `schemas.py`: 주제 10개(확정), 선별·후보·검증 요청·해설가 출력·카드 규격(pydantic). 검증 노드도 같은 규격을 쓴다
- `verifier.py`: 검증관. E2B 4단계, SKILL.md 판독 (예정)

## 들어오고 나가는 데이터
- 들어옴: `pipeline/`의 정리된 항목, 루트 `memory.py`의 사용자 기억, MCP 도구 결과(`<data>` 원문)
- 나감: 큐레이터 `{selected, plans, verify, stats}`, 해설가 `{users: [{cards, rejected, format_failed}], stats}`, 루프 이벤트

## 관련
- 루트 `models.py`·`providers.py`: 역할별 모델 호출 / 루트 `mcp_server.py`: 루프가 부르는 도구

## 할 일
- [ ] 해설가 실제 모델 검수(같은 항목 for_me 3쌍·반려 이유). 로컬 모델로 한도 걱정 없이 돌릴 수 있다
- [ ] 선별 기준 편차: Gemini 34건, 대체 모델 94건. 로컬 모델 결과와 같은 데이터로 비교
- [ ] Langfuse 스팬 전송 제한 시간(5초) 초과로 최상위 스팬이 빠진 트레이스 1건. 제한 시간 조정 여부 결정
- [ ] `verifier.py`와 되돌림 2개, 에이전트별 도구 호출 상한 (뼈대 완성 후)
