# tests/ CHANGELOG

- 2026-09-30 · golden/select_2026-09-30.json(뉴스 189건 O/X, Claude Code 채점)·run_select_2026-09-30.json, check_promo에 새 선별 기준 문구 · 선별 모델을 Claude Haiku(생각 끔)로 바꾼 뒤 첫 채점 · 9/30 재현율 87.5%(79.0~92.9)·정밀도 74.8%(65.6~82.2), 9/27(gemma3) 대비 정밀도 ↑ 재현율 ↓

- 2026-09-29 · check_claude_cli에 생각 끄기 2항목(--settings, 모델표 큐레이터·게이트만 옵션 전달) · 9/29 첫 구독 실행 50분 중 선별 31분 · 21항목 통과

- 2026-09-28 · check_claude_cli에 도구 6항목(목록을 시스템 프롬프트에, 약속을 tool_calls로, 코드 블록, 모르는 이름은 글, 최종 답 그대로, 이전 호출·결과 이어붙임), check_models: 도구 필요한 호출도 구독부터(gemma3만 건너뜀) · 구독 도구 호출 · 19항목 통과, 실제 루프 1회(8.6초·2단계·도구 1번)

- 2026-09-28 · models/check_claude_cli.py 추가(인자·API 키 안 넘김·새 프로세스 그룹·여러 턴·한도 529와 30분 건너뜀·503들), check_models: 개발 모델표 구독 1순위·구독 성공·한도면 기다리지 않고 전환, 전환 순서 기대값 갱신, --offline(실제 호출 건너뜀) · Claude 구독 전환 · check_claude_cli 13·check_models --offline 통과, 실제 구독 호출 1회(Haiku 3.6초, JSON)

- 2026-09-28 · check_headline: 가중치 -5 주제도 큰 소식에 남음(계획안 부록 C) · 예외 처리 표 대조 · 18항목 통과

- 2026-09-28 · check_deliver: 묶음 메일 항목 대신 받는 사람·제목(본인·가짜 프로필·운영), 개발 모드도 사용자마다 한 통·한 통 실패는 그 사용자만. check_mail_layout: 묶음 항목 대신 빈 행 메일 머리·개발 모드 표시 없음 · 실전용 메일 · 통과

- 2026-09-28 · check_card_why에 관련 카드 경로(근거 이유·최근 본 게시자 빠짐) · 9/28 월요일 관련 카드 · 8항목 통과

- 2026-09-28 · models/check_fallback_errors.py 추가(다른 제공자 도구 호출·결과는 글로, Gemini 호출은 서명 그대로, 검증 한 건 오류는 미완료·다음 건 계속), db/check_tables에 시드가 기존 상태를 안 바꾸는지 · 9/28 사고 두 건 · 7항목 통과

- 2026-09-28 · check_apply에 변경 이력 6항목(관리자 승인·차단 순서, 같은 상태 안 남음, 마지막 결정, 401·403, 초대 코드 가입, 계정 삭제 시 이력 삭제), check_tables 표 13개·check 제약 6개 · 승인 이력 · 24항목 통과

- 2026-09-27 · access/check_apply.py 추가(신청 제출·동의·고침·승인 전 403·일반 사용자 목록 403·관리자 신청 수·목록·승인·차단·화면·실제 계정 관리자), db/check_tables JSONB 칸 10개(users.application) · 이용 신청과 승인 탭 · 18항목 통과

- 2026-09-27 · check_tool_updates에 새 버전 카드가 5번째여도 먼저 확인, check_weekly에 원격 전용 제외 · 로직 점검 · 전체 오프라인 검수 46개 통과(실제 모델·E2B·실제 수집 검수 run_today·check_models 등 10개는 제외, run_dedupe는 캐시가 없으면 실제 수집을 해서 432초)

- 2026-09-27 · pipeline/check_weekly.py 추가(금요일에만·카드 없으면 안 붙음·실제 DB 합계·주제·설치 수·맨 아래·없으면 그대로·안전한 링크·새 버전 칸) · 금요일 이번 주 요약 · 9항목 통과

- 2026-09-27 · pipeline/check_tool_updates.py 추가(제목 버전·비교·하루 1장·카드 모양·plan 맨 앞·겹침·장애·발송 전 재검증·실제 DB 30일), run_daily 검수는 collect_items 세 값에 맞춤 · 받아 본 도구의 새 버전 알림 · 12항목 통과

- 2026-09-27 · golden/ 추가: select_2026-09-27.json(뉴스 141건 O/X와 기준, Claude Code 채점), run_select_2026-09-27.json(9/27 실행 판정), fetch_select.py(트레이스에서 판정 꺼내기, 모델 호출 없음), score_select.py(재현율·정밀도·윌슨 95% 구간) · 계획안 품질 지표 선별 재현율·정밀도 · 9/27 재현율 95.2%(86.9~98.4) 목표 달성, 정밀도 63.2%(53.1~72.2) 미달: 잘못 통과 35건은 에세이·의견·질문 글·개인 실험·발언 보도

- 2026-09-27 · agent/check_card_why.py 추가(관심 주제·쓰는 도구 근거, 단어 경계, 가중치 0·음수, 대체 문구, 120자, pick_why), check_rollback에 교체 카드 이유에 교체 사정 없음 · 카드 이유 근거화 · check_card_why 7·check_rollback 통과

- 2026-09-27 · pipeline/check_promo.py 추가(홍보·연재 빼기와 이유, 진짜 소식·도구는 남김, 선별·해설가·큐레이터 프롬프트 기준 들어 있음) · 가치 낮은 뉴스 거르기·카드 문장 기준 · 8항목 통과

- 2026-09-27 · agent/check_owners.py 추가(게시자 파싱·7일·하루 한 건·후보 반영·memory 창), feedback/check_appendix_c 가짜 모델이 같은 소식 묶기에 답하고 관련 카드 후보는 검수용 도구만 · 9/23 같은 소식 묶기 추가 뒤로 부록 C 검수가 깨져 있었다(실제 도구 목록이 쌓여 검수용 도구가 후보에서도 밀림) · check_owners 8·check_appendix_c 7항목 통과

- 2026-09-26 · verify/check_mcp_now.py 추가(MCP만·한도·시간 예산·실패 계속·요청 먼저 저장, 요청 상태 메모, 요청 없으면 검증 안 함, 위험 신호 근거·인용 정리), check_skill_now는 pipeline/presend를 보게, run_daily --fake에 MCP 발송 전 검증 항목·가짜 설치 방법 답·요청 행 뒷정리 · MCP 발송 전 검증 · check_mcp_now 18항목 통과

- 2026-09-25 · pipeline/run_daily.py: briefings 조회에 ORDER BY id, 행 하나를 UPDATE한 뒤 전후·실행 계획별 순서를 비교하는 항목 추가 · --fake 간헐 실패(ORDER BY 없는 목록 비교가 행 위치·계획에 따라 갈림, 고치기 전 이 항목으로 기존 장애 전후 비교 실패 재현) · 47항목 2회 통과

- 2026-09-25 · pipeline/check_autorestart.py: 강제 종료 호출 확인, 실제 uvicorn 시험을 정상 종료(8011)와 끝나지 않는 연결을 연 강제 종료(8012) 둘로 · 자동 재시작 멈춤 사고 · 16항목 통과

- 2026-09-25 · agent/check_importance.py에 같은 모델 재시도·중요도 낮은 뉴스 빼기·10건 미만이면 그대로 3항목 추가 · 9/24·25 메일 점검 뒤 수정 · 14항목 통과

- 2026-09-23 · agent/check_importance.py 추가(뉴스만·요청 내용·반올림·단계 번호·범위·실패는 그대로·키 없음·비용·모델표·가짜 모델이면 안 부름), check_same_story 기본 모델을 same_story 단일 모델로 · Jev 중요도·같은 소식 모델 지정 · 11항목 통과, Jev·네트워크 미사용

- 2026-09-23 · agent/check_headline.py 추가(뽑힘·대표 등급·점수·1칸/2칸·기준 미달 없음·모델 장애·맨 위 고정·같은 소식 빠짐·5장·본 소식·가중치 -5·importance 기본값·카드·메일 표시·curator.run 연결) · 오늘의 큰 소식 · 17항목 통과

- 2026-09-23 · agent/check_same_story.py 추가(앞 하나만·채우지 않음·제목만·한 장이면 안 부름·잘못된 id·장애·해설가 순서·pick_for_user 연결), pipeline/run_daily.py 가짜 모델에 같은 소식 묶기 답 · 같은 소식 겹침 빼기 · 8항목 통과

- 2026-09-23 · agent/check_topic_guide.py 추가(주제 10개 정의·프롬프트에 한 줄씩·단어 아닌 내용 규칙·개발 주제 경계·model_release 사례 제외·프롬프트 1,800자) · 주제 분류 보강 · 6항목 통과, 모델·네트워크 미사용

- 2026-09-23 · pipeline/check_watchdog.py 추가(정상·앱 무응답·브리핑 없음·미발송·DB 실패·알림 시각 30분·06~22시·같은 문제 한 번·새 문제·다음 날·못 보낸 알림 재시도·본문에 값 없음·실제 DB 읽기) · 앱 바깥 감시 · 14항목 통과, 메일 미발송

- 2026-09-23 · pipeline/check_autorestart.py 추가(HEAD 바뀜·한 번만·기능 브랜치·커밋 안 한 수정·06~09시·실행 중·다음 예정 10분·git 없음·끄기·예약 루프 연결·실제 uvicorn 신호 종료) · 코드 수정 뒤 자동 재시작 · 14항목 통과, DB·모델·메일 미사용

- 2026-09-23 · verify/check_skill_now.py 추가(스킬만·관련 카드 포함·중복 한 번·요청 모양·요청 행 먼저 저장·이미 판독 건너뜀·한 실행 한도·스킬 없으면 무동작·실패해도 계속) · 스킬 발송 전 판독 · 10항목 통과, 네트워크·모델·DB 미사용

- 2026-09-23 · sources/check_skillsmp.py 추가(주제어마다 호출·중복 합침·이미 본 주소 제외·게시자당 상한·별 수 정렬·항목 규격·키 없으면 건너뜀·일부 실패 진행·전부 실패면 오류) · 스킬 수집 · 11항목 통과, 네트워크 미사용

- 2026-09-22 · pipeline/run_daily.py --fake가 검수용 프로필을 도는 동안만 승인했다가 실패해도 원래 상태로 되돌림(approved_while_testing) · 사용자가 검수를 마쳤다며 가짜 프로필 A·B·C(user 1·2·3)를 하루 실행과 메일에서 빼기로 해 DB에서 blocked로 바꿨는데, 이 검수는 하루 실행과 같은 대상 선택(승인된 is_test)을 거쳐 그대로면 깨진다 · run_daily --fake·check_deliver·check_reject_rate·check_access 통과, 검수 뒤 blocked 유지 확인

- 2026-09-22 · pipeline/check_mail_layout.py 추가(근거 링크 규칙 HTML·텍스트, 요일, 종류 칩, 머리 되풀이 없음, body, 카드마다 trace_id, 웹앱 색 토큰) · 메일 가독성 · 12항목 통과, 네트워크·DB 미사용

- 2026-09-21 · web/common.py 검수 클라이언트를 https://testserver로 · APP_BASE_URL이 https면 세션 쿠키가 secure로 발급되는데 TestClient가 http로 요청해 쿠키가 실리지 않아 로그인이 필요한 검수가 401로 깨졌다(코드 버그 아님, 환경 의존) · check_design·check_auth·check_settings·check_briefings·check_feedback·check_ask·check_access 통과

- 2026-09-21 · agent/check_reject_rate.py 추가(실제로 반려됐던 항목 재투입, 무관한 대조 항목은 계속 반려되는지 같이 확인) · 해설가 반려율 · 5항목 통과. 앱 8000 포트와 fetch_article을 실제로 쓴다

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
