# agent/ CHANGELOG

- 2026-09-16 · curator.replan_failed(되돌림 1: 대체 선택·비움, 모델 장애면 그 도구만 빠짐), schemas ReplanDecision·Card.verification_note, 해설가 입력에 검증 결과, reverify 스팬 이름 verify:reverify · 세션 8 되돌림 5단계 · check_rollback 16항목 통과
- 2026-09-15 · verifier.py(설치 방법 판단·probe_mcp, 스킬 판독·정규식 비교·공식 생략, reverify), schemas McpProbePlan·SkillJudgment · 세션 8 검증관 4단계 · check_verifier 17항목 통과(삽입 문장에 모델이 넘어가도 정상이 아니라 확인 필요)
- 2026-09-15 · skill_check.py 추가(원문 주소 변환·SkillsMP API로 GitHub 원문, 절단 전 전체 정규식, 보이지 않는 문자는 [U+XXXX] 인용) · 세션 8 검증관 3단계 read_skill · check_skill_read 13항목 통과, 실제 스킬 6개(공식 3·SkillsMP 3) 오탐 0
- 2026-09-15 · probe.py 추가(설치 명령 파싱·가드·4단계·인증 요구 감지·probes 저장), loop MCP 읽기 제한 120 → 240초 · 세션 8 검증관 2단계 probe_mcp · check_probe 10항목 통과(server-everything 22초 도구 13, mcp-server-fetch 28초, DeepWiki 원격, Apify 401, brave-search BRAVE_API_KEY 감지)
- 2026-09-15 · curator.pick_related·RELATED_PROMPT, schemas.RelatedPicks·Card.related, explainer가 related 항목도 카드로 · F3-b 관련 카드(월요일 최대 3장, 사용자 결정) · run_daily --fake 관련 카드 5항목·부록 C 기준 2 통과
- 2026-09-15 · explainer.answer·AnswerOutput 추가, loop.run에 max_tool_calls · 질문창 W2(부록 E 도구 최대 3회·600자·확인한 곳) · check_ask 20항목, run_loop·run_explainer --fake 회귀 통과
- 2026-09-15 · curator: 모델이 고른 후보를 주제 가중치로 안정 정렬, 결과·트레이스에 사용자별 weights · 부록 C "다음 날 큐레이터가 가중치를 읽어 정렬" · check_appendix_c 6항목·run_daily --fake 통과
- 2026-09-15 · 해설가 출력에 relevance(1~5) 추가·3 미만 반려, 초안 카드(DraftCard)로 긴 요약·빈 값을 검증 노드에 넘김, 프롬프트에 두 문장·120자·빈 값 금지·관련도 기준, 원문은 source_url 우선·skip_fetch면 요약만, 알림 문구 합치기 · 세션 7 결정 1·5·6, format_failures.json 예시 4건 · run_explainer --fake 통과

- 2026-09-15 · structured: JSON이 아닌 답은 형식 실패로 처리, curator: 후보 단계 입력 상한(뉴스 60·도구 20, 이유 60자·요약 120자, 가중치·출처·최신·별 수 순) · 실제 실행에서 후보 140건이 로컬 문맥 8192토큰을 채워 답이 잘렸고 빈 후보로 통과해 B·C 메일이 "오늘 볼 만한 게 없었음"으로 나감 · run_daily --fake 회귀 3항목 통과

- 2026-09-14 · 큐레이터·해설가 모델 장애 단위 건너뜀, structured 실패 예시에 제공자·모델 기록·예시 전부 보관, loop 결과에 제공자·모델 · 로컬 모델 전환과 모델 장애 결정(세션 4) · run_daily --fake 29항목 통과

- 2026-09-14 · explainer.explain_item에 feedback 인자 추가 · 검증 노드가 돌려보낸 이유를 붙여 1회 재시도하려고 · run_daily --fake에서 영어 첫 응답이 재시도로 복구됨 확인

- 2026-09-14 · explainer.py·glossary.md 추가, JSON 규격 응답을 structured.py로 분리 · 계획안 5장 해설가·부록 B 4, 무료 한도 절약으로 항목당 원문 1회·모델 1회 · run_explainer --fake 8항목 통과, 실제 모델 검수는 한도 초기화 후

- 2026-09-14 · curator.py·schemas.py 추가, loop.py 토큰 합계·원문 반환 · 계획안 5장 큐레이터·부록 B 1~3 · 1차 형식 실패 4건(사고·추론 토큰이 출력 한도 소진) → 사고 minimal·추론 끔 적용 후 run_curator 통과(호출 13회·63초·형식 실패 1회 재시도로 복구)
- 2026-09-14 · 할 일에 Langfuse 전송 제한 시간 초과 건 추가 · run_loop 실제 모델 실행 중 스팬 묶음 전송이 5초를 넘어 최상위 스팬 1개 누락 · run_loop 통과(실제 안녕·도구 1개)
- 2026-09-14 · loop.py 개발 모드 안내 로그, tracing.py config 연결·trace_url() 추가 · DEV_MODE 승인·값 출력 금지 규칙 · run_loop 루프 동작 9항목 통과, 실제 모델은 OpenRouter 키 401로 미통과
- 2026-09-13 · loop.py 직접 판단 루프 구현 · 착수 10번 · run_loop 루프 동작 8항목 통과, 실제 모델 실행은 키 없어 미실행
- 2026-09-13 · README에 할 일 절 추가, 파일 상태 갱신 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · tracing.py 추가 · 모든 LLM·도구 호출을 스팬으로 남기고 Langfuse 장애 시 로컬 로그 대체(절대 규칙 10) · tests/models/check_models.py에서 로컬 모드 trace_id 발급 확인
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
