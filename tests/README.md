# tests/

기능별 검수 스크립트. 실행은 루트에서 `uv run python -m tests.<폴더>.<파일>`.

## 파일
- `docs/check_folder_docs.py`: 폴더 README 30줄·할 일·CHANGELOG 형식·긴 줄표 / `docs/check_readme.py`: 루트 README 사양·부록 F 트리
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import → `env/check_env.json` / `env/check_config.py`: .env 로더·값 비출력
- `env/check_env_example.py`: `.env.example` 키 목록·`.env` git 무시 / `env/check_docker.py`: GitHub Actions `ci` 4단계, compose(app 1개)·Dockerfile
- `models/check_claude_cli.py`: Claude 구독 공급자(가짜 실행기) / `models/check_fallback_errors.py`: 제공자 전환 중 도구 기록 변환·검증 한 건 오류 격리 / `models/check_anthropic.py`: Anthropic 제공자(가짜 HTTP: 변환·도구 호출·구조화 출력·429/5xx 전환·키 없음)와 운영 모델표 [Haiku 5.5, gpt-4o-mini] / `models/check_models.py`: 모델표, 운영 제공자 전환(429·503·529·연결·타임아웃·키 없음), 개발 구독만(503 1회 더·529 건너뜀), 모델 장애, 옵션 전달, 호출 간격 + 개발 6역할 실제 구독 호출
- `models/check_local_models.py`·`check_groq.py`: 로컬 Ollama VRAM·도구 호출·한글 실측, Groq 목록 API·도구 호출·한도 → `models/local_models.json`·`groq_models.json`
- `access/check_apply.py`: 이용 신청·관리자 승인 탭 / `access/check_access.py`: 초대제(승인 전 403 6종·코드 기한·횟수·관리자 API)와 공개 데모(비로그인 200·버튼 없음·사용자 노출 없음·분당 60회·색인)
- `db/check_tables.py`: 표 18개·연결 문자열 변환·is_test·briefings 빈 행 구조 + Supabase 실제 생성·개발 프로필 A·B·C
- `sources/`: `check_fallbacks.py` 재시도·전날 결과·긱뉴스 링크 / `check_news_window.py` 창 48시간·보낸 항목·제외 규칙 / `check_catalog_title.py` 제목 규칙·upsert 갱신 / `backfill_titles.py` 기존 행 보정 / `check_skillsmp.py` 스킬 수집 / `run_today.py` 수집 건수 → `report.md` / `check_claude_notes.py` Claude 릴리스 노트 파서(고정 HTML) / `check_github_search.py` GitHub 검색 소스(가짜 응답) / `check_mcp_list.py` 레지스트리 목록 48시간·예산·쪽 재시도(가짜 클라이언트)
- `pipeline/run_dedupe.py`: 정리·중복 제거 단위 검사 + 전후 건수 / `check_promo.py`: 책 연재·행사 홍보 뉴스 빼기, 선별·해설가 문장 기준 / `check_tool_updates.py`: 받아 본 도구 새 버전 알림 / `check_weekly.py`: 금요일 이번 주 요약
- `pipeline/run_daily.py`: `--fake`는 검증 노드·저장·멱등·모델 장애·빈 행·도구 목록 쌓기·조회 순서 고정·옵션(2000-01-01 저장 후 삭제), 없으면 실제 한 번(`--users --limit`) → `daily_report.json`, 형식 실패는 `format_failures.json` / `check_validate.py`: 검증 노드 마지막 수단(for_me 첫 문장만) 8항목
- `pipeline/check_deliver.py`: 메일 렌더링(trace_id·이스케이프·빈 행)·개발 모드 묶음 한 통·운영 모드 사용자별 한 통 + sent_at 멱등 + 가짜 SMTP 발송·실패 알림 + DB 깨우기 + API 키 / `check_mail_layout.py`: 메일 모양 44항목(토큰 색·preheader·배지·도구 머리 사례·세 무게·마크 alt·빈 날 선별 기록·판정·버튼·13px·기호·60KB 등, 리디자인 2라운드)
- `pipeline/check_scheduler.py`: 가짜 시계로 06:00 검증·예열·실행·발송·따라잡기, 실행 실패 30분 재시도·빠진 사용자만·DB 실패·실패 알림 한 번 / `check_autorestart.py`: 자동 재시작 / `check_watchdog.py`: 앱 바깥 감시 / `check_cron.py`: Railway 크론 차례별 할 일·같은 차례 정기 실행과 지금 만들기 중복 막기·웹 외부 작업 모드(지금 만들기 요청·/api/w1 409)
- `feedback/check_appendix_c.py`: 부록 C 기준 3개(관심없음 3회 순위·트레이스 -3, 써봤음 → F3-b 후보 노션 계열 맨 위, 만료 링크 기록 0) / `check_merge.py`: 주간 합치기(30일 무반응 주제만 피드백만큼 되돌림·설정 값 유지·멱등)
- `mcp/list_tools.py`: 도구 6개·키 검문 / `e2b/smoke.py`: E2B 생성·폐기·차단 / `verify/`: check_probe(실제 E2B), check_skill_read(정규식·원문), check_verifier(가짜 모델로 판단·판독·상태·카드 칸), check_rollback(되돌림 1·2 발동), check_skill_now(스킬 발송 전 판독), check_mcp_now(MCP 발송 전 검증·검증 메모·위험 신호 근거), check_probe_labels(도움말 CLI·키 필요·버전 바뀜 표시), run_real(실제 5건), fixtures/ 가짜 스킬
- `app/check_main.py`: uvicorn main:app 기동, /, /api/health, /mcp 확인. `start()`는 다른 검수도 쓴다(서버 출력은 임시 폴더 로그)
- `web/`: check_auth·check_settings·check_briefings·check_feedback·check_ask(`--live-gate`)·check_rules(API 세션·남의 데이터·디자인 기준 CSS)·check_design(run_stats·item_meta, 토큰·자동=수동 다크·대비 계산·CSS와 HTML style 색은 토큰만·SVG 안전·크기 예산·head 링크·금지 사항, PWA·메일 PNG), check_screens(화면 전부 × 라이트·자동 다크·수동 다크 × 1366(높이 650)·390·360 자동 검수 11항목·브랜드 + 스크린샷, 화면마다 node 따로 240초, `cdp_screens.mjs`, 판정·도구 머리 사례 `verdict_cases.json`), check_protect(운영 /docs 404·/static 허용 목록·AI UA 403·X-Robots-Tag·TDM·고지), check_minify(배포용 경량화 결과 JS 원본 그대로·node --check·화면당 CSS 42KB·gzip 10KB + 8002번 앱을 Edge 헤드리스로 열어 콘솔 오류 확인, `cdp_console.mjs` 사용). check_legal(방침·약관 공개 페이지), check_gmail_api(Gmail API 연결·발송, 가짜 구글), check_protect2(보호 2차 43항목: 워터마크 왕복·메일·함정 24시간·요청 수 제한·DB 실패 통과, 시각은 guard.clock으로 조작, 검수 행은 지움). tests/web/common이 RATE_LIMIT_OFF=1을 기본으로 둔다 · `check_support`(공통 푸터 정적 검사·/policy·/support·문의 저장·관리자 메일·Reply-To·429·꿀단지·중복·관리자 목록/처리함)
- `golden/`: 선별 골든셋. `fetch_select.py`(그날 판정을 트레이스에서) → `score_select.py`(재현율·정밀도·신뢰구간, 앞선 날짜에 나온 기사를 뺀 new_only도), check_score_select / `agent/run_loop.py`: 가짜 모델로 루프 동작 9항목 + 현재 모델표 해설가로 실제 "안녕"·도구 1개(통과 조건)
- `agent/check_injection.py`: 인젝션 방어 18항목(정리·지시 문장 10종·오탐·출력 검사·설치 명령·수집·감싸기·해설가·질문 답·루프 도구 거부), `--live`는 지시를 심은 항목 3건으로 실제 해설가 / `agent/check_topic_guide.py`: 주제 경계가 선별 프롬프트에 빠짐없이·길이 상한 / `check_same_story.py`: 같은 소식 빼기 / `check_owners.py`: 게시자 반복 줄이기 / `check_card_why.py`: 카드 이유 근거 / `check_headline.py`: 오늘의 큰 소식(메일은 '업계 큰 소식' 리드) / `check_importance.py`: 중요도(Jev, 개발 모드는 Jev 실패분만 구독 대체) / `agent/run_curator.py`: 오늘 수집 + 가짜 프로필 2개로 큐레이터 실행 → `agent/curator_report.json`
- `agent/run_explainer.py`: `--fake`는 가짜 모델로 카드·반려·재시도 8항목, 없으면 실제 카드 + for_me 3쌍 → `explainer_report.json` / `check_reject_rate.py`: 반려됐던 항목 재투입·대조군 반려 5항목

## 들어오고 나가는 데이터 / 관련
- 들어옴: 각 폴더 코드, 실제 외부 응답 / 나감: 검수 결과 JSON (값은 출력하지 않음). 모든 주요 폴더와 관련

## 할 일
- [ ] 개발 모드는 구독만이라(2026-10-05) 구독 한도에 걸리면 그 묶음·카드가 빠진다. 실제 실행 검수는 디버깅 `--users 1 --limit 40`, 전량은 하루 한 번
