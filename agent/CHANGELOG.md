# agent/ CHANGELOG

- 2026-09-14 · explainer.explain_item에 feedback 인자 추가 · 검증 노드가 돌려보낸 이유를 붙여 1회 재시도하려고 · run_daily --fake에서 영어 첫 응답이 재시도로 복구됨 확인

- 2026-09-14 · explainer.py·glossary.md 추가, JSON 규격 응답을 structured.py로 분리 · 계획안 5장 해설가·부록 B 4, 무료 한도 절약으로 항목당 원문 1회·모델 1회 · run_explainer --fake 8항목 통과, 실제 모델 검수는 한도 초기화 후

- 2026-09-14 · curator.py·schemas.py 추가, loop.py 토큰 합계·원문 반환 · 계획안 5장 큐레이터·부록 B 1~3 · 1차 형식 실패 4건(사고·추론 토큰이 출력 한도 소진) → 사고 minimal·추론 끔 적용 후 run_curator 통과(호출 13회·63초·형식 실패 1회 재시도로 복구)
- 2026-09-14 · 할 일에 Langfuse 전송 제한 시간 초과 건 추가 · run_loop 실제 모델 실행 중 스팬 묶음 전송이 5초를 넘어 최상위 스팬 1개 누락 · run_loop 통과(실제 안녕·도구 1개)
- 2026-09-14 · loop.py 개발 모드 안내 로그, tracing.py config 연결·trace_url() 추가 · DEV_MODE 승인·값 출력 금지 규칙 · run_loop 루프 동작 9항목 통과, 실제 모델은 OpenRouter 키 401로 미통과
- 2026-09-13 · loop.py 직접 판단 루프 구현 · 착수 10번 · run_loop 루프 동작 8항목 통과, 실제 모델 실행은 키 없어 미실행
- 2026-09-13 · README에 할 일 절 추가, 파일 상태 갱신 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · tracing.py 추가 · 모든 LLM·도구 호출을 스팬으로 남기고 Langfuse 장애 시 로컬 로그 대체(절대 규칙 10) · tests/models/check_models.py에서 로컬 모드 trace_id 발급 확인
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
