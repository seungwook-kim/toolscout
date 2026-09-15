# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 6 · 2026-09-15 · n8n 제거, 앱 안 예약과 Gmail 직접 발송 (main 머지 완료)
  - 결정(사용자): n8n 구조 제외, 07:00 실행·08:00 발송은 FastAPI 앱 안에서 예약, 개발 모드도 ADMIN_EMAILS(본인)에게만 실제 발송 허용
  - 끝난 것: `pipeline/scheduler.py`(07:00·08:00, 놓친 실행 22:00 전 따라잡기, 실행 끝난 뒤 발송, 발송 실패 10분 간격 2번 더), `pipeline/deliver.py` Gmail SMTP 발송(보낸 사용자만 sent_at), `routes/w1.py` 수동 실행·발송·상태, n8n 폴더·compose 서비스·CI 단계·문서 제거
  - 검수: check_scheduler 11항목, check_deliver 24항목(가짜 SMTP), check_main·check_readme·check_folder_docs·check_env_example 통과, CI 4단계 success(b1e72f1)
  - 실제 메일: 9/15 브리핑(사용자 1·카드 5·반려 1·호출 11·416초)을 개발 모드로 ADMIN_EMAILS에 Gmail SMTP 발송, 받은편지함 도착 확인(카드마다 trace_id). 트레이스 https://us.cloud.langfuse.com/project/cmu0jv4a1000iad0doj6r99it/traces/74fd811dfd31cc41164570abf9b27ed9
  - 관찰: gemma3 첫 로드 30초 초과로 선별 1묶음 groq 전환, groq 429 2회·gemini 429 1회로 카드 1장 openrouter. MCP 레지스트리는 이번엔 성공
  - 미완: 앱 상시 실행(예약은 앱이 떠 있어야 돈다)과 다음 날 07:00·08:00 자동 실행 확인
  - 결정 필요: PC 켤 때 앱 자동 시작 여부, gemma3 첫 로드 타임아웃, groq 429. 계획안 위험 목록의 "강사 기준: n8n 필수/가산점" 확인
  - 다음 시작점: 앱을 켜 두고 다음 날 07:00 실행·08:00 메일 자동 도착 확인 (뼈대 완성)

- 세션 5 · 2026-09-15 · 전량 하루 실행, 08:00 발송 준비·기록, n8n W1 (main 머지 완료)
  - 끝난 것: 전량 실행(사용자 2명·카드 7·반려 5·호출 23·토큰 입력 56,604·출력 10,610·650초·전환 없음), 메일 본문(`pipeline/briefing_mail.py`, 카드 전체·카드마다 trace_id), 발송함·sent_at 기록(`pipeline/deliver.py`), n8n용 API(`routes/w1.py`), W1 워크플로우(`n8n/workflows/W1_daily.json`), CI에 n8n 가져오기
  - 검수: check_deliver 19항목, check_workflows 13항목, CI 6단계 success(n8n 기동·가져오기 포함), 9/14 브리핑 개발 모드 콘솔 발송 2통·sent_at 7행
  - 미완: n8n에서 W1 실제 실행(로컬 Docker 없음, n8n 2.38은 Node 24 필요인데 로컬 Node 20), 실제 메일 도착(개발 모드는 발송 금지, GMAIL_USER 비어 있음), 피드백 버튼(W3)
  - 결정 필요: n8n을 어디서 돌릴지(Docker Desktop·Railway·Node 24), 실제 메일 테스트를 운영 모드로 할지, MCP 레지스트리 ReadTimeout 2회 연속(도구 후보 0건), gemma3 첫 로드 24.5초
  - 다음 시작점: n8n 실행 환경 결정 → 자격 증명 2개 만들고 W1 켜기 → 07:00·08:00 실제 실행과 메일 도착 확인 (뼈대 완성 정의)

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
