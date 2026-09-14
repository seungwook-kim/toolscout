# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일 절·CHANGELOG 형식·긴 줄표
- `docs/check_readme.py`: 루트 README 사양(절, 배지, mermaid, 이모지 규칙)
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json`
- `env/check_env_example.py`: `.env.example` 키 21개(DEV_MODE·OPENROUTER 포함), `.env` git 무시
- `env/check_config.py`: .env 로더 해석·깨진 줄 경고·값 비출력, 키는 설정됨/비어있음만
- `env/check_docker.py`: 로컬 docker 없으면 GitHub Actions `ci` 결과(4단계)로 판정, compose·Dockerfile 정적 검사
- `models/check_models.py`: 운영·개발 모델표, 429·503·529 전환, DEV_MODE 전환, 변환 + 개발 모델 4역할 실제 호출(통과 조건)
- `db/check_tables.py`: 표 9개·연결 문자열 변환·is_test + Supabase 실제 생성·가짜 프로필 2개(통과 조건)
- `sources/run_today.py`: 9곳 실제 수집, 300건 ±20% 넘으면 필터 강화 재측정 → `today_counts.json`, `report.md`
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 오늘 전후 건수 → `pipeline/dedupe_counts.json`
- `mcp/list_tools.py`: 실제 HTTP로 도구 6개·키 검문·거부 규칙 → `mcp/list_tools_result.json`
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인
- `agent/run_loop.py`: 가짜 모델로 루프 동작 9항목 + 현재 모델표 해설가로 실제 "안녕"·도구 1개(통과 조건)

## 들어오고 나가는 데이터
- 들어옴: 각 폴더의 코드, 실제 외부 소스 응답 / 나감: 검수 결과 JSON (값은 출력하지 않음)

## 관련
- 모든 주요 폴더 (기능 하나 끝날 때마다 여기에 검수 스크립트를 남긴다)

## 할 일
- [ ] OpenRouter 키 재발급·DATABASE_URL 줄 수정 후 check_models, check_tables, run_loop 재실행
