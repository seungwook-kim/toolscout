# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 4 · 2026-09-14 · 개발용 로컬 모델(Ollama)과 첫 실제 하루 실행 (main 머지 완료)
  - 끝난 것: Windows Ollama 0.34.0 설치(WSL2는 다운로드가 초당 78KB로 제외), 로컬 모델 실측(`docs/local-model.md`), 개발 제공자 순서 ollama → groq → gemini → openrouter, Groq 모델 확정, run_daily `--users`·`--limit`, 형식 실패 예시 파일 누적, 모델 장애 사용자·카드 단위 건너뜀(전원 실패 종료 코드 2), 카드 0건 empty_reason 행(briefings 기본키 이전), 계획안 모델 장애 행·한글 비율 어절 60%
  - 모델: 큐레이터·게이트 gemma3:12b(8.96GiB, 도구 호출 미지원), 해설가·검증관 groq qwen3.8-27b. qwen3:14b(9.82GiB)는 삭제
  - 첫 실제 실행(`--users 1 --limit 40`): 브리핑 1명·카드 3·반려 0·제외 0, 호출 8(ollama 4·groq 4, 전환 없음), 토큰 입력 22,963·출력 4,567, 486초, 형식 실패 2회 모두 재시도 복구, 트레이스 https://us.cloud.langfuse.com/project/cmu0jv4a1000iad0doj6r99it/traces/7c45d4178f4dfda3995a82f886e938f9
  - 검수: check_models·check_groq·check_tables·run_daily --fake 30항목·run_explainer --fake·check_folder_docs·check_readme 통과
  - 결정 필요: gemma3:12b 첫 로드 24.5초(30초 타임아웃 근접), MCP 레지스트리 ReadTimeout으로 도구 후보 0건, 전량 실행 시간(Groq 30초 간격)
  - 다음 시작점: 전량 실행(사용자 2명) 한 번 → 이메일 발송(sent_at 기록, empty_reason 행 포함) + n8n W1

- 세션 3 · 2026-09-14 · 큐레이터·해설가·검증 노드·저장·하루 실행 (가짜 모델 검수 통과, main 머지 완료)
  - 끝난 것 (main 머지): 큐레이터(선별·사용자별 후보·검증 요청), JSON 규격 응답·1회 재시도(`agent/structured.py`), 해설가·용어집 30개, 검증 노드(`pipeline/validate.py`), 저장(`pipeline/persist.py`), 하루 실행(`pipeline/run_daily.py`), MCP 수집 별 수 24시간 캐시·신규 20·버전 업 10, 개발 모델 사고·추론 설정과 호출 간격
  - 검수: run_curator 실제 통과(호출 13·63초·선별 94·두 사용자 겹침 0·검증 요청 5), run_explainer --fake 8항목, run_daily --fake 21항목(Supabase 실제 저장·재실행 멱등·발송 사용자 건너뜀) 통과
  - 무료 모델 형식 실패: 큐레이터 1차 12회(재시도 후 4건 실패, 사고·추론 토큰이 출력 한도 소진) → 설정 조정 후 1회(재시도로 복구)
  - 미완: 실제 모델 run_daily·run_explainer. Gemini·OpenRouter 무료 하루 한도 모두 소진으로 큐레이터 첫 호출에서 멈춤, 저장 0건
  - 결정 필요: 기본·대체 모델이 둘 다 실패할 때 처리(지금은 실행 전체가 멈춤), 한글 비율 어절 기준 60% 확인, 카드 0건 사용자 발송 방식
  - 다음 시작점: 9월 15일 16:00 KST 이후 `tests.pipeline.run_daily` 실제 한 번 → 이메일 발송(sent_at 기록) + n8n W1

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
