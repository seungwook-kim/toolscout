# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 2 · 2026-09-14 · 지난 결정 반영과 막힌 검수 마무리 (4번 통과, main 머지 완료)
  - 끝난 것 (main 머지): Docker CI (GitHub Actions 4단계 성공), `config.py` .env 로더(값 출력 금지 규칙), psycopg와 연결 문자열 자동 변환, Gemini·Anthropic 클라이언트 닫힘 버그, 529 전환, 계획안 부록 F, mcp/ 용도, 벤처비트 제외, DEV_MODE 모델표·OpenRouter, users.is_test·가짜 프로필 2개, MCP·해커뉴스 수집 필터
  - 4번 통과: check_env / check_tables (Supabase 표 9개, is_test 칸, 가짜 프로필 id 1·2) / check_models (개발 모델 4역할 실제 호출) / run_loop (nex-n2.5-pro 안녕·도구 1개, Langfuse 트레이스)
  - 개발 모델표는 실측으로 재배정: gemma-4는 무료 공급자 429 반복으로 제외, 검증관·해설가 nex-n2.5-pro, 게이트·큐레이터 대체 nex-n2.5-mini
  - 결정 필요: 수집량 기준 (필터 적용·재측정 후 912건, MCP 7일 신규 등록만 648건), MCP 수집 137초 캐시 방식, Langfuse 스팬 전송 제한 시간(5초 초과로 최상위 스팬 1개 누락)
  - 다음 시작점: 큐레이터 (`agent/curator.py`)

- 세션 1 · 2026-09-13 · 0단계·1단계 앞부분 (착수 1~12번)
  - 끝난 것 (main 머지): 1 폴더 구조·문서, 2 루트 README, 3 pyproject·환경 검사, 4 .env.example, 6 models.py·tracing.py, 7 db.py(Supabase 전용), 8 sources 10곳, 9 pipeline, 10 loop.py, 11 mcp_server.py, 12 main.py, 폴더 README 할 일 절, .gitignore
  - 미완: 5 docker는 `feat/05-docker` 브랜치(docker 미설치로 compose config·compose up app 미검증, 머지 보류)
  - 키 없어 미실행인 검수: models 실제 호출, db Supabase 생성, loop 실제 모델 "안녕"·도구 1개
  - 결정됨: DB는 Supabase 하나(SQLite 안 씀), 로컬 작업 도구 파일은 저장소 제외, 해커뉴스는 OR 의미(optionalWords), 로컬 .env는 `uv run --env-file .env`로 읽음(python-dotenv 불필요)
  - 결정 필요: Docker 검수를 GitHub Actions로 할지(.github/ 추가), .env 키·Supabase 연결 문자열·Postgres 드라이버(psycopg), Anthropic 529 전환 포함, 수집량 기준(MCP 7일 1,964건·HN 189건), 벤처비트 429, 부록 A 트리, mcp/ 폴더 용도
  - 다음 시작점: 큐레이터 (`agent/curator.py`)
