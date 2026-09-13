# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일 절·CHANGELOG 형식·긴 줄표
- `docs/check_readme.py`: 루트 README 사양(절, 배지, mermaid, 이모지 규칙)
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json`
- `env/check_env_example.py`: `.env.example` 키 19개, `.env` git 무시
- `env/check_docker.py`: compose config·Dockerfile (feat/05-docker 브랜치에 있음)
- `models/check_models.py`: 모델표·429·503 전환·공급자별 변환, 키 있으면 실제 호출
- `db/check_tables.py`: 표 9개·Postgres DDL·제약, DATABASE_URL 있으면 Supabase에 실제 생성
- `sources/run_today.py`: 10곳 실제 수집 → `sources/today_counts.json`, `sources/report.md`
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 오늘 전후 건수 → `pipeline/dedupe_counts.json`
- `mcp/list_tools.py`: 실제 HTTP로 도구 6개·키 검문·거부 규칙 → `mcp/list_tools_result.json`
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인

## 들어오고 나가는 데이터
- 들어옴: 각 폴더의 코드, 실제 외부 소스 응답
- 나감: 검수 결과 JSON (통과/미통과)

## 관련
- 모든 주요 폴더 (기능 하나 끝날 때마다 여기에 검수 스크립트를 남긴다)

## 할 일
- [ ] `agent/` 루프 "안녕"·도구 1개 실행 (착수 10번)
- [ ] 키·Docker·Supabase 준비 후 미실행 검수 재실행
