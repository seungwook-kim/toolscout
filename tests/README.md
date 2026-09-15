# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일·CHANGELOG 형식·긴 줄표 / `docs/check_readme.py`: 루트 README 사양·부록 F 트리
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json`
- `env/check_env_example.py`: `.env.example` 키 22개(DEV_MODE·OPENROUTER·GROQ 포함), `.env` git 무시
- `env/check_config.py`: .env 로더 해석·깨진 줄 경고·값 비출력, 키는 설정됨/비어있음만
- `env/check_docker.py`: 로컬 docker 없으면 GitHub Actions `ci` 결과로 판정(CI는 n8n 워크플로우 가져오기도 함), compose·Dockerfile 정적 검사
- `n8n/check_workflows.py`: W1 JSON 노드 종류·버전(n8n 2.38)·크론·시간대·연결·부르는 API·메일 필드·개발 모드 분기·비밀값 없음
- `models/check_models.py`: 모델표, 제공자 순서 전환(429·503·529·연결·타임아웃·키 없음), 모델 장애, 옵션 전달, 호출 간격 + 개발 4역할 실제 호출
- `models/check_local_models.py`: 로컬 Ollama 모델별 VRAM·도구 호출·한글 요약 3건·선별 20건 시간 → `models/local_models.json`
- `models/check_groq.py`: Groq 목록 API에 모델표 모델이 있는지, 실제 도구 호출·JSON·한글 한 줄, 한도 헤더 → `models/groq_models.json`
- `db/check_tables.py`: 표 9개·연결 문자열 변환·is_test·briefings 빈 행 구조 + Supabase 실제 생성·가짜 프로필 2개(통과 조건)
- `sources/run_today.py`: 9곳 실제 수집, 300건 ±20% 넘으면 필터 강화 재측정 → `today_counts.json`, `report.md`
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 오늘 전후 건수 → `pipeline/dedupe_counts.json`
- `pipeline/run_daily.py`: `--fake`는 검증 노드·저장·멱등·모델 장애·빈 행·옵션 29항목(2000-01-01 저장 후 삭제), 없으면 실제 한 번(`--users --limit`) → `pipeline/daily_report.json`, 형식 실패는 `pipeline/format_failures.json`
- `pipeline/check_deliver.py`: 메일 렌더링(카드마다 trace_id·이스케이프·빈 행) + 발송함·sent_at 멱등(2000-01-02) + W1 API 키 검문
- `mcp/list_tools.py`: 실제 HTTP로 도구 6개·키 검문·거부 규칙 → `mcp/list_tools_result.json`
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인. `start()`는 다른 검수도 쓴다(서버 출력은 임시 폴더 로그)
- `agent/run_loop.py`: 가짜 모델로 루프 동작 9항목 + 현재 모델표 해설가로 실제 "안녕"·도구 1개(통과 조건)
- `agent/run_curator.py`: 오늘 수집 + 가짜 프로필 2개로 큐레이터 실행 → `agent/curator_report.json`
- `agent/run_explainer.py`: `--fake`는 가짜 모델로 카드·반려·재시도·원문 확인 필요 8항목, 없으면 실제 카드 + for_me 3쌍 → `agent/explainer_report.json`

## 들어오고 나가는 데이터 / 관련
- 들어옴: 각 폴더 코드, 실제 외부 응답 / 나감: 검수 결과 JSON (값은 출력하지 않음). 모든 주요 폴더와 관련

## 할 일
- [ ] 원격 무료 한도(Gemini 하루 20회, OpenRouter 하루 50회)는 로컬 모델이 먼저 받으므로 전량 실행만 하루 한 번