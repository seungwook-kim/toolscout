# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일 절·CHANGELOG 형식·긴 줄표
- `docs/check_readme.py`: 루트 README 사양(절, 배지, mermaid, 이모지 규칙)
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json`
- `env/check_env_example.py`: `.env.example` 키 21개(DEV_MODE·OPENROUTER 포함), `.env` git 무시
- `env/check_config.py`: .env 로더 해석·깨진 줄 경고·값 비출력, 키는 설정됨/비어있음만
- `env/check_docker.py`: 로컬 docker 없으면 GitHub Actions `ci` 결과(4단계)로 판정, compose·Dockerfile 정적 검사
- `models/check_models.py`: 모델표, 429·503·529 전환, DEV_MODE, 옵션(온도·사고·추론) 전달, 호출 간격 + 개발 모델 4역할 실제 호출
- `db/check_tables.py`: 표 9개·연결 문자열 변환·is_test + Supabase 실제 생성·가짜 프로필 2개(통과 조건)
- `sources/run_today.py`: 9곳 실제 수집, 300건 ±20% 넘으면 필터 강화 재측정 → `today_counts.json`, `report.md`
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 오늘 전후 건수 → `pipeline/dedupe_counts.json`
- `pipeline/run_daily.py`: `--fake`는 가짜 모델로 검증 노드·저장·멱등 21항목(2000-01-01로 저장 후 삭제), 없으면 실제 한 번 → `pipeline/daily_report.json`
- `mcp/list_tools.py`: 실제 HTTP로 도구 6개·키 검문·거부 규칙 → `mcp/list_tools_result.json`
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인. `start()`는 다른 검수도 쓴다(서버 출력은 임시 폴더 로그)
- `agent/run_loop.py`: 가짜 모델로 루프 동작 9항목 + 현재 모델표 해설가로 실제 "안녕"·도구 1개(통과 조건)
- `agent/run_curator.py`: 오늘 수집 + 가짜 프로필 2개로 큐레이터 실행 → `agent/curator_report.json`
- `agent/run_explainer.py`: `--fake`는 가짜 모델로 카드·반려·재시도·원문 확인 필요 8항목, 없으면 실제 카드 + for_me 3쌍 → `agent/explainer_report.json`

## 들어오고 나가는 데이터 / 관련
- 들어옴: 각 폴더 코드, 실제 외부 응답 / 나감: 검수 결과 JSON (값은 출력하지 않음). 모든 주요 폴더와 관련

## 할 일
- [ ] 무료 한도(Gemini 하루 20회, OpenRouter 하루 50회) 때문에 실제 호출 검수는 하루 한 번, 초기화 뒤에 몰아서
