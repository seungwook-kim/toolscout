# routes/ CHANGELOG

- 2026-10-09 · pages: /onboarding 추가, 승인됐고 프로필이 비면 /, /history, /settings는 /settings 대신 /onboarding으로(프로필이 차 있으면 /onboarding은 /로) · 첫 설정 화면 분리(리디자인 합의) · check_settings 통과
- 2026-10-09 · auth.mark_login(마지막 로그인 시각·방법)을 비밀번호 로그인·가입 직후(password)·구글(google)·서명 토큰(link)에서 부름, db.py users.last_login_at·last_login_method, GET /api/admin/users에 두 칸 · 사용자 결정 (가) "마지막 로그인 시각이랑 방법 남겨줘"(로그인마다 쌓지 않음) · check_auth 34·check_apply·check_access 통과
- 2026-10-08 · signup.py·google.py(신규: 이메일 인증번호 가입·비밀번호 로그인·구글 OAuth), auth.py에서 로그인 링크 요청 제거, invite.py는 승인·사용자 관리만(초대 코드·신청서 제거), pages /signup·/pending(/invite는 /pending으로), demo는 고정 예시 · 사용자 결정: 첫 화면은 회원가입 + 구글 로그인, 아이디 = 이메일, 인증번호 확인 뒤 가입, 비밀번호 로그인, 관리자 승인 뒤 사용 · check_auth 32·check_access·check_apply 통과
- 2026-10-07 · settings: JOBS_EXTERNAL=1(Vercel)이면 지금 만들기는 DB에 요청만 남기고 상태도 DB로 · w1: 같은 모드에서 실행·발송 409 · 사용자 결정 "vercel + railway" · check_cron 통과
- 2026-09-28 · invite.py: 상태가 실제로 바뀔 때마다 status_changes에 이력(관리자 변경은 admin·바꾼 관리자, 초대 코드 가입은 invite_code), GET /api/admin/status-changes(최근 50건), 사용자 목록에 마지막 결정. db.py status_changes 표(계정 삭제 시 이력 CASCADE, 바꾼 관리자 삭제 시 SET NULL) · 사용자 요청 "누가 언제 승인했는지" · check_apply 24·check_tables·check_access·check_settings 통과

- 2026-09-27 · invite.py에 이용 신청(POST·GET /api/apply, 동의 필수·이유 10자 이상·승인 전만·다시 내면 고침)과 관리자 신청 목록(GET /api/admin/applications), 사용자 목록에 신청 내용. auth /api/me에 관리자만 대기 신청 수. users에 application·applied_at 칸, 개발자 본인 계정 users.is_admin 켬(권한 판단은 계속 ADMIN_EMAILS) · 사용자 요청(로그인해도 승인 전에는 메일 없음, 신청서, 관리자만 보는 승인 탭) · check_apply 18·check_access·check_tables 통과

- 2026-09-16 · 초대제(auth.require_approved·invite.py 코드 사용과 관리자 API)와 공개 데모(demo.py, 분당 60회·robots), pages에 /invite·/admin/invites·noindex · 가입은 초대제, 데모는 읽기 전용 (2026-09-16 사용자 결정) · check_access 30항목 통과
- 2026-09-15 · briefings.py 응답에 카드마다 item_meta(별 수·버전·출처·공개 시각), 그날 run_stats(선별·반려·검증) · 새 화면 파이프라인·도구 메타 칸 (사용자 승인: 읽기 전용으로 채우기) · check_design A 5항목·check_briefings 통과
- 2026-09-15 · ask.py 키워드 검색에 items.description(수집 원문 설명) 포함 · 쌓인 도구 목록을 질문 후보로 · check_ask 20항목 통과
- 2026-09-15 · ask.py 추가(POST·GET /api/ask) · 웹앱 본체 5단계 질문창 W2, 부록 E · check_ask 20항목 통과 (흔한 단어 "MCP"가 847건 걸려 최신순 60건에서 어제 카드가 빠지던 문제를 일치 점수순으로 수정)
- 2026-09-15 · feedback.py 추가(웹 세션·메일 서명 링크) · 웹앱 본체 4단계 W3 · check_feedback 14항목·check_appendix_c 6항목 통과 (/api/feedback/link/note를 {id}/note가 먼저 잡던 문제를 :int로 수정)
- 2026-09-15 · briefings.py 추가(오늘·날짜별 브리핑, 날짜 목록, 검색) · 웹앱 본체 3단계·6단계 API · check_briefings 11항목 통과

- 2026-09-15 · settings.py 추가(프로필·기억 지우기·계정 삭제·지금 만들기) · 웹앱 본체 2단계 · check_settings 10항목 통과

- 2026-09-15 · auth.py(매직링크 로그인·세션), tokens.py(서명 토큰·1회용), pages.py(화면 라우팅) 추가 · 웹앱 본체 1단계 로그인 · check_auth 15항목 통과 (1회용 판정을 rowcount로 하던 버그를 RETURNING으로 수정)

- 2026-09-15 · w1.py를 수동 실행·발송·상태 API로 변경(발송함·발송 기록 API 삭제) · n8n 제외, 예약은 앱 안에서 · check_deliver API 2항목 통과

- 2026-09-15 · w1.py 추가(하루 실행 시작·상태·발송함·발송 기록), main.py에 연결 · n8n W1이 앱을 부르는 경로 · check_deliver API 4항목 통과(키 없으면 401·발송함 2통·발송 기록 멱등·상태)

- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
