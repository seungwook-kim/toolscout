# routes/ CHANGELOG

- 2026-10-31 · ask.find_candidates가 뜻이 가까운 항목(embeddings.search)을 키워드 상위 20개와 RRF로 합침, 키·표가 없거나 호출이 실패하면 키워드 순서 그대로 · 한국어로 풀어 쓴 질문은 키워드로 못 찾아서 · 합성 질문 60개 적중 47% → 77%(의미 검색만 시험 임베딩으로 대신), check_ask·check_embeddings 통과
- 2026-10-30 · ask.keywords가 한글 이름(큐웬·코덱스 등)의 영어 표기를 원래 낱말 뒤에 덧붙이고 낱말 상한 5 → 8, 사전 파일이 없으면 확장 없이 동작 · 질문이 한글로 읽은 이름이면 영어 제목에 안 걸려서 · 합성 질문 60개 후보 5안 적중 40% → 47%, check_ask·check_ask_terms 통과
- 2026-10-14 · briefings: 카드 topic·topic_label·item_meta 조립을 pipeline/persist.card_extras로 옮겨 메일 발송(deliver.outbox)과 같이 씀(published_at …Z 형식 그대로) · 메일 메타 줄이 웹과 같은 값을 쓰게(복사 금지) · check_deliver 통과(웹 응답 형식 변화 없음)
- 2026-10-09 · support.py 신규(POST /api/support 비로그인 가능·저장·관리자 메일 한 통·Reply-To·1시간 3건/10건 제한·꿀단지·중복 거름, 관리자 GET /api/admin/support·POST .../handled), pages에 /policy·/support, INDEXABLE·robots Allow · 로그인 못 하는 사람도 문의할 수 있게(문의자 주소로는 자동 메일 없음) · check_support 통과
- 2026-10-09 · pages: 로그인 없이 열리는 GET /privacy·/terms 추가, protect.INDEXABLE과 robots.txt에 두 주소 허용 · 구글 OAuth 앱을 프로덕션으로 게시하려면 홈페이지·개인정보처리방침·약관 링크가 필요해서 · check_legal, check_protect 통과
- 2026-10-09 · google.py: 관리자 전용 GET /admin/gmail/connect와 GET /api/admin/gmail, 같은 콜백에서 state 종류(k=gmail)로 로그인과 Gmail 발송 연결을 가름 · 구글 콘솔에 등록된 리디렉션 주소가 둘뿐이라 새 콜백을 못 만든다 · tests.web.check_gmail_api, check_auth 통과
- 2026-10-09 · guard: '차단 중' 결과도 1분만 기억하고 DB를 다시 봄 · 운영 확인에서 차단 행을 지워도 따뜻한 서버가 만료(24시간)까지 403을 냈다 · check_protect2 통과
- 2026-10-09 · guard.py(신규: 함정 링크 24시간 차단·요청 수 제한), watermark.py(신규: 사용자별 0폭 문자 표식·해독 명령), tokens.derive, protect 미들웨어에 차단 확인, briefings·demo에 제한·표식, pages robots에 함정 경로 Disallow, main에 guard 라우터 · 무단 복제 2차 보호(사용자 결정: 워터마크·함정 링크·요청 수 제한은 넣고 JS 난독화는 안 함) · check_protect2 43항목 통과
- 2026-10-09 · protect.py(신규: AI 크롤러 UA 403·X-Robots-Tag·TDM 헤더·/static 허용 목록), pages에 AI 크롤러 이름별 robots.txt와 /.well-known/tdmrep.json, 루트 main.py는 make_app(docs)로 운영(DEV_MODE=0)에서 /docs·/redoc·/openapi.json 닫음 · 무단 복제·AI 크롤링 1차 보호(사용자 지시) · check_protect·check_access·check_rules 통과
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
