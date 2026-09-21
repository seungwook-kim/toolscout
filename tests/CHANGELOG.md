# tests/ CHANGELOG

- 2026-09-21 · sources/check_catalog_title.py(제목 규칙·두 경로 공용·upsert 갱신·빈 값 보호)와 sources/backfill_titles.py(기존 행 보정) 추가 · 도구 목록 제목이 저장소 이름으로 굳던 문제 · 9항목 통과, 보정 40건

- 2026-09-21 · pipeline/run_daily.py 관련 카드 검수용 도구 3개에 별 수(90만대) 부여 · 관련 카드 후보는 겹친 말 수 > 별 수 순으로 상위 30건만 모델에 가는데, 별 수가 없던 검수용 도구가 쌓인 실제 MCP 56건에 밀려 후보에서 빠지면서 검수 3항목이 실패하고 있었다(제품 코드는 정상) · run_daily --fake 전체 통과

- 2026-09-21 · sources/check_news_window.py 추가(창 48시간·30시간 전 남고 50시간 전 빠짐·도구 창 7일 유지·어제 밀린 기사 오늘 재후보·이미 보낸 항목 seen_urls로 제외·제외 규칙 프롬프트) · 뉴스 창 48시간 · 10항목 통과, 네트워크·모델 미사용

- 2026-09-16 · access/check_access.py 추가(승인 전 403 6종·코드 기한·횟수·관리자 API·하루 실행 대상·데모 비로그인·사용자 노출 없음·분당 60회·색인), check_tables에 표 12개·초대제 칸·데모 프로필 · 초대제와 공개 데모 · 30항목 통과
- 2026-09-16 · check_deliver에 묶음 메일 4항목(제목·목차·구역·이스케이프), 개발 모드 묶음 실패는 전부 미발송, 운영 모드(DEV_MODE=0) 사용자별 한 통 2항목 추가 · 개발 모드 메일 묶기 · 27항목 통과
- 2026-09-16 · verify/run_real.py 추가(도구 목록에서 큐레이터가 실제 모델로 요청 → 06:00과 같은 verifier.run, 단계별 성공률·시간·위험 신호), check_verifier에 설치 정보 있으면 모델 안 부름·자리표시자·도커·저장 수 · 세션 8 7단계 · check_verifier 21항목 통과
- 2026-09-16 · verify/check_rollback.py 추가(되돌림 1 대체·비움·장애, 되돌림 2 회복·확인 필요·공유·상한, 스팬), check_scheduler 06:00 검증 5항목(가짜 시계가 잠들기 전에 따로 도는 작업을 먼저 돌림), check_design 검증관 칸 문구 · 세션 8 5단계 · 전부 통과
- 2026-09-15 · verify/check_verifier.py 추가 · 세션 8 검증관 4단계 · 17항목 통과, check_tables(skill_reviews skipped 제약)
- 2026-09-15 · verify/check_skill_read.py와 fixtures(가짜 스킬 3: 외부 전송·판독 지시 삽입·깨끗함) 추가 · 세션 8 검증관 3단계 · 13항목 통과
- 2026-09-15 · verify/check_probe.py 추가, check_tables 표 11개·JSONB 9칸(verify_requests·probes 칸 추가) · 세션 8 검증관 2단계 · 10항목·check_tables·list_tools·run_loop 통과
- 2026-09-15 · e2b/smoke.py 추가 · 세션 8 검증관 1단계 E2B 연결 · 생성 954ms·echo 307ms·폐기 150ms, Python 3.11·Node 20·npm 10, deny_out 뒤 외부 통신 차단 확인
- 2026-09-15 · web/check_design.py 추가, check_rules의 옛 CSS 두 칸 항목을 참고 파일 style 기준으로, check_tables JSONB 칸 수 5 → 6(briefings.run_stats) · 디자인 기준 적용·읽기 전용 데이터 · 통과
- 2026-09-15 · run_daily --fake 관련 카드 5항목(두 프로필 다른 추천·이름 일치 우선·related 저장·재노출 0), check_deliver 관련 칸, 부록 C 기준 2를 실제 F3-b 후보 순서로 · W4-d · 통과
- 2026-09-15 · feedback/check_merge.py 추가, check_scheduler에 월요일 합치기 4항목 · W4-c 주간 기억 합치기 · 10항목·23항목 통과
- 2026-09-15 · run_daily --fake에 도구 목록 쌓기 4항목, check_tables items 열에 description · W4-b 관련 카드 후보 목록 · 통과
- 2026-09-15 · check_scheduler에 실행 재시도·빠진 사용자만 다시·DB 실패 간격·실패 알림 한 번, check_deliver에 send_alert·wake_db · W4-a 재실행·실패 알림 · 19항목·check_deliver 통과
- 2026-09-15 · web/check_rules.py 추가 · 웹앱 본체 7단계 규칙(세션·남의 데이터 거부·반응형·긴 줄표·SSE와 공개 MCP 제외) · 11항목 통과, 세션 없이 열리는 API는 5개(상태·로그인 요청·로그아웃·메일 서명 링크 2)
- 2026-09-15 · check_briefings에 지난 브리핑 화면 항목 추가 · 웹앱 본체 6단계 · 12항목 통과
- 2026-09-15 · web/check_ask.py 추가 · 부록 E 검수 기준(범위 밖 5개 out·호출 0·한도 그대로, 한도 초과, 1턴→2턴 설치 명령) · 가짜 모델 20항목 통과, --live-gate 로컬 gemma3 예시 5/5
- 2026-09-15 · web/check_feedback.py, feedback/check_appendix_c.py 추가 · 웹앱 본체 4단계 W3, 부록 C 검수 기준 · 14항목·6항목 통과 (F3-b 관련 카드는 없어서 기준 2는 도구 후보 정렬로 확인)
- 2026-09-15 · web/check_briefings.py 추가, web/common second_client(두 번째 사용자, lifespan 없이) · 웹앱 3단계 · 11항목 통과

- 2026-09-15 · web/check_settings.py 추가, check_scheduler 알림 시각마다 발송 · 웹앱 2단계 · check_settings 10항목·check_scheduler 통과

- 2026-09-15 · web/common.py·web/check_auth.py 추가, check_main 루트 기대값(로그인으로 이동), check_tables 표 10개, check_env_example APP_BASE_URL · 웹앱 본체 1단계 로그인 · check_auth 15항목·check_main·check_tables·check_env_example 통과

- 2026-09-15 · sources/check_fallbacks.py 추가 · 세션 7 결정 4·5 (MCP 재시도·전날 결과, 긱뉴스 외부 링크) · 7항목 통과

- 2026-09-15 · check_models: 429 60초 뒤 같은 제공자 재시도·해설가 groq→gemma3 대체·도구 필요하면 gemma3 건너뜀·로컬 첫 호출 90초·이후 30초, check_scheduler: 06:55 예열 · 세션 7 결정 2·3 · check_models·check_scheduler 통과

- 2026-09-15 · run_daily --fake에 긴 요약 자르기·빈 요약 자가 수정·관련도 2 반려 검사, 가짜 해설가 답에 relevance · 세션 7 결정 1·6 · run_daily --fake·run_explainer --fake 통과

- 2026-09-15 · run_daily --fake에 회귀 검사 3항목(잘린 JSON 형식 실패, 후보 단계 상한·순서) · 빈 후보 메일 버그 · 통과

- 2026-09-15 · 개발 프로필 3개(A·B·C)에 맞춰 check_tables·check_deliver·run_curator·run_daily 조건 수정(A·B 비교는 그대로) · 프로필 C 추가 · check_tables·check_deliver·run_daily --fake·run_explainer --fake 통과

- 2026-09-15 · pipeline/check_scheduler.py 추가, check_deliver를 가짜 SMTP 발송 검사로 변경, n8n/check_workflows.py 삭제, check_docker·check_readme·check_folder_docs·check_env_example에서 n8n 제거·SCHEDULER_ENABLED 추가, 검수 서버는 예약 끔 · n8n 제외 결정 · check_scheduler 11·check_deliver 24항목, check_readme·check_folder_docs·check_env_example·check_main 통과

- 2026-09-15 · check_docker가 CI 6단계(app 4·n8n 2) 모두 success인지 확인 · CI에 n8n 워크플로우 가져오기 추가 · check_docker 통과(ced74b9, n8n 기동·가져오기 success)

- 2026-09-15 · n8n/check_workflows.py 추가, CI에 n8n 기동·워크플로우 가져오기 단계 · W1 워크플로우 검수(로컬 Node 20이라 n8n 2.38 실행 불가, CI 컨테이너로 가져오기) · check_workflows 13항목 통과

- 2026-09-15 · pipeline/check_deliver.py 추가, daily_report.json 전량 실행 결과로 갱신 · 08:00 발송 검수 · check_deliver 19항목 통과, 전량 run_daily 실제 통과(4항목)

- 2026-09-14 · pipeline/daily_report.json·format_failures.json 첫 기록, run_daily --fake에 수집 결과 꺼내기 검사 · 첫 실제 하루 실행 · run_daily 실제 통과(4항목), --fake 30항목 통과

- 2026-09-14 · models/check_groq.py 추가 · GROQ_API_KEY 발급 후 모델표 groq 모델 확정 · 통과(qwen3.8-27b·gpt-oss-20b 목록·도구 호출·JSON 성공, llama-3.3-70b는 404), check_models 개발 4역할 첫 제공자 실제 호출 통과

- 2026-09-14 · models/check_local_models.py 추가, check_models 제공자 순서·모델 장애·ollama·groq 검사, check_tables briefings 빈 행 구조, check_env_example GROQ 키, run_daily --fake 모델 장애·빈 행·옵션 검사 · 로컬 모델 전환(세션 4) · check_models·check_tables 통과, run_daily --fake 29항목 통과

- 2026-09-14 · pipeline/run_daily.py 추가, check_main.start 서버 출력을 PIPE에서 임시 로그 파일로 변경 · 하루 실행 검수. 읽지 않는 PIPE 버퍼가 차서 도구 호출 20~40회 뒤 서버가 멈추는 것을 재현·확인 · run_daily --fake 21항목 통과, 수정 후 같은 서버에 호출 200회 통과

- 2026-09-14 · agent/run_explainer.py 추가 · 해설가 검수(가짜 모델 경로 + 실제 for_me 비교) · --fake 8항목 통과, 실제 모드는 무료 한도 초기화 후 실행

- 2026-09-14 · agent/run_curator.py 추가, check_models에 옵션 전달·호출 간격 검사 · 큐레이터 검수 · 2차 통과(선별 94·두 사용자 겹침 0·검증 요청 5). Gemini 무료 하루 한도 소진으로 대체 경로로 확인
- 2026-09-14 · run_today 선별 호출 수·MCP 분할 검사, check_tables items.stars_checked_at 확인, run_loop 실패 시 ExceptionGroup 원인 기록 · MCP 상위 30·Gemini 해설가 결정 반영 · 통과(run_today 161건, check_models Gemini 4역할, run_loop Gemini 안녕·도구 1개, 첫 실행 1회 일시 오류 후 통과)
- 2026-09-14 · 실제 연결 검수 재실행 · .env DATABASE_URL 줄 수정·OpenRouter 키 재발급 후 · check_tables 통과(Supabase 표 9개·가짜 프로필 2개), check_models 통과(개발 모델 4역할 실제 호출, 1회 ReadTimeout 후 재실행 성공), run_loop 통과(nex-n2.5-pro 안녕·도구 1개, Langfuse 트레이스 확인)
- 2026-09-14 · sources/run_today.py 필터 재측정 방식으로 변경, check_models·check_tables·run_loop에 DEV_MODE·Supabase·실제 모델 조건 추가 · 수집 필터·개발 모델표 승인 반영 · run_today 통과(943→912건, 목표 초과), 나머지는 키 문제로 실제 호출 부분 미통과
- 2026-09-14 · check_docker.py를 GitHub Actions CI 결과로 판정하도록 변경 · 로컬 docker 없이 5번 검수 · 통과(CI 4단계 success, 정적 8항목)
- 2026-09-14 · env/check_config.py 추가 · .env 값 출력 금지 규칙과 config 로더 · 통과(5항목)
- 2026-09-13 · agent/run_loop.py 추가 · 착수 10번 루프 동작 · 통과(8항목), 실제 모델 실행은 ANTHROPIC_API_KEY 없어 미실행
- 2026-09-13 · app/check_main.py 추가 · 착수 12번 uvicorn 기동 · 통과(5항목), docker compose up app은 feat/05-docker 검수로 넘김
- 2026-09-13 · mcp/list_tools.py, list_tools_result.json 추가 · 착수 11번 도구 목록·키 검문 · 통과(7항목), 긱뉴스 HTML 403이라 GitHub 페이지로 가져오기 확인
- 2026-09-13 · pipeline/run_dedupe.py, dedupe_counts.json 추가 · 착수 9번 전후 건수 · 통과(7항목), 2,233 → 2,229 → 2,227
- 2026-09-13 · sources/run_today.py, today_counts.json, report.md 추가 · 착수 8번 소스별 건수 실측(원본 리포트 없어 새로 작성) · 구조 검사 4항목 통과
- 2026-09-13 · README에 할 일 절 추가, check_folder_docs가 할 일 절도 검사 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · db/check_tables.py 추가 · db.py 검수(Supabase 전용, SQLite 제외 결정 반영) · 통과(8항목), Supabase 실제 생성은 미설정으로 미실행
- 2026-09-13 · models/check_models.py 추가 · models.py 검수 · 통과(10항목), 실제 API 호출은 키 없어 미실행
- 2026-09-13 · env/check_env_example.py 추가 · .env.example 키 목록과 .env 무시 검수 · 통과(4항목)
- 2026-09-13 · env/check_env.py, check_env.json 추가 · 기술 고정 설치 후 langgraph 미설치 실측 · 통과(9항목, pip check는 uv pip으로 실행)
- 2026-09-13 · docs/check_readme.py 추가, 추적되던 __pycache__ 제거 · 루트 README 사양 검수 · 통과(15항목)
- 2026-09-13 · docs/check_folder_docs.py 추가 · 폴더 문서 규칙 검수 · 통과(9개 폴더)
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
