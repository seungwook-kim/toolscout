# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일·CHANGELOG 형식·긴 줄표 / `docs/check_readme.py`: 루트 README 사양·부록 F 트리
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json` / `env/check_config.py`: .env 로더·값 비출력
- `env/check_env_example.py`: `.env.example` 키 목록·`.env` git 무시 / `env/check_docker.py`: GitHub Actions `ci` 4단계, compose(app 1개)·Dockerfile
- `models/check_models.py`: 모델표, 제공자 순서 전환(429·503·529·연결·타임아웃·키 없음), 모델 장애, 옵션 전달, 호출 간격 + 개발 4역할 실제 호출
- `models/check_local_models.py`·`check_groq.py`: 로컬 Ollama VRAM·도구 호출·한글 실측, Groq 목록 API·도구 호출·한도 → `models/local_models.json`·`groq_models.json`
- `db/check_tables.py`: 표 10개·연결 문자열 변환·is_test·briefings 빈 행 구조 + Supabase 실제 생성·개발 프로필 A·B·C
- `sources/check_fallbacks.py`: MCP 레지스트리 재시도·전날 결과, 긱뉴스 외부 링크 / `sources/run_today.py`: 9곳 실제 수집 건수 → `report.md`
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 전후 건수
- `pipeline/run_daily.py`: `--fake`는 검증 노드·저장·멱등·모델 장애·빈 행·도구 목록 쌓기·옵션(2000-01-01 저장 후 삭제), 없으면 실제 한 번(`--users --limit`) → `daily_report.json`, 형식 실패는 `format_failures.json`
- `pipeline/check_deliver.py`: 메일 렌더링(trace_id·이스케이프·빈 행) + sent_at 멱등 + 가짜 SMTP 발송·실패 알림 + DB 깨우기 + API 키
- `pipeline/check_scheduler.py`: 가짜 시계로 예열·실행·발송·따라잡기, 실행 실패 30분 재시도·빠진 사용자만·DB 실패·실패 알림 한 번
- `feedback/check_appendix_c.py`: 부록 C 기준 3개(관심없음 3회 순위·트레이스 -3, 써봤음 → F3-b 후보 노션 계열 맨 위, 만료 링크 기록 0) / `check_merge.py`: 주간 합치기(30일 무반응 주제만 피드백만큼 되돌림·설정 값 유지·멱등)
- `mcp/list_tools.py`: 실제 HTTP로 도구 6개·키 검문·거부 규칙 → `mcp/list_tools_result.json`
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인. `start()`는 다른 검수도 쓴다(서버 출력은 임시 폴더 로그)
- `web/`: check_auth·check_settings·check_briefings·check_feedback·check_ask(`--live-gate`)·check_rules(API 세션·남의 데이터·디자인 기준 CSS)·check_design(run_stats·item_meta, 보충 CSS 토큰만·공통 마스트헤드·금지 사항, PWA)
- `agent/run_loop.py`: 가짜 모델로 루프 동작 9항목 + 현재 모델표 해설가로 실제 "안녕"·도구 1개(통과 조건)
- `agent/run_curator.py`: 오늘 수집 + 가짜 프로필 2개로 큐레이터 실행 → `agent/curator_report.json`
- `agent/run_explainer.py`: `--fake`는 가짜 모델로 카드·반려·재시도·원문 확인 필요 8항목, 없으면 실제 카드 + for_me 3쌍 → `agent/explainer_report.json`

## 들어오고 나가는 데이터 / 관련
- 들어옴: 각 폴더 코드, 실제 외부 응답 / 나감: 검수 결과 JSON (값은 출력하지 않음). 모든 주요 폴더와 관련

## 할 일
- [ ] 원격 무료 한도(Gemini 하루 20회, OpenRouter 하루 50회)는 로컬 모델이 먼저 받으므로 전량 실행만 하루 한 번
