# pipeline/ CHANGELOG

- 2026-09-16 · run_daily.target_user_ids는 approved 사용자만(운영은 데모 프로필 포함), deliver.outbox에서 데모 프로필 제외 · 초대제 도입으로 대상이 달라짐 · check_access·check_deliver 통과
- 2026-09-16 · 개발 모드 메일을 프로필마다 한 통에서 전부 묶어 한 통으로(briefing_mail.combine, deliver 묶음 발송·mails 칸) · 프로필이 전부 내 받은편지함으로 오는데 4통이 따로 와서 (2026-09-16 사용자 결정) · check_deliver 27항목 통과
- 2026-09-16 · verification.save_requests 저장 수를 returning으로 셈 · 실제 실행에서 rowcount -1이 나와 저장 수가 -5로 보고됨 · check_verifier(저장 10·중복 저장 0) 통과
- 2026-09-16 · rollback.py(되돌림 1·2, attach), run_daily에 검증 요청 저장·되돌림 두 개·검증 칸·run_stats verified·rollbacks, scheduler 06:00 검증(W1-a, 따로 도는 작업·늦게 켜지면 실행 뒤) · 세션 8 5단계, 계획안 조정 "검증관 크론은 W1과 분리" · check_rollback·check_scheduler(검증 5항목 추가)·run_daily --fake·check_deliver 통과
- 2026-09-15 · verification.py 추가(verify_requests 큐·skill_reviews·카드 칸), briefing_mail 검증 결과 줄과 고정 문구 두 개 · 세션 8 검증관 4단계 · check_verifier 17항목·check_deliver 통과
- 2026-09-15 · run_daily가 사용자마다 run_stats(선별·반려·제외·검증 요청·검증 0)를 briefings에, persist가 items.published_at(원문 공개 시각) 저장 · 화면 파이프라인 칸과 도구 공개 시점 (사용자 승인) · run_daily --fake·check_design 통과
- 2026-09-15 · persist.related_pool, run_daily 월요일(또는 --related) 관련 카드, briefing_mail "이번 주 관련 MCP·스킬" 칸 · F3-b 관련 카드(주 1회, 월요일 최대 3장) · run_daily --fake 관련 카드 5항목·check_deliver 통과
- 2026-09-15 · scheduler: 월요일 06:55 예열 뒤·하루 실행 전에 memory.merge_weights(늦게 켜져도 실행 전 한 번, 실패해도 실행은 계속), 상태에 last_merge · 계획안 W4 주간 기억 합치기 · check_scheduler 23항목 통과
- 2026-09-15 · persist.save_catalog, run_daily가 큐레이터 뒤 선별 통과 도구를 items에 쌓음(catalog_saved), items.description · 관련 카드(F3-b) 후보 목록, 사용자 결정 · run_daily --fake 도구 목록 4항목 추가 통과, check_tables(Supabase 열 추가) 통과
- 2026-09-15 · scheduler: 하루 실행 실패·빠진 사용자 30분 뒤 그 사용자만 2번 더, 끝내 실패하면 ADMIN_EMAILS 실패 알림, 발송 끝내 실패도 알림, 06:55 DB 깨우기 / deliver.send_alert, persist.wake_db · 계획안 "W1이 죽고 재실행"·W4 실패 알림·Supabase 깨우기, 내일 07:00 뼈대 확인 전에 한 번 실패로 하루가 비지 않게 · check_scheduler 19항목·check_deliver 통과
- 2026-09-15 · 메일 카드에 피드백 버튼 서명 링크(뉴스 관심없음·이상함, 도구는 써봤음까지) · 웹앱 본체 4단계 W3 · check_feedback·check_deliver 통과
- 2026-09-15 · run_daily user_ids(설정 화면 지금 만들기는 본인만)·pool_size 저장, deliver 알림 시각 필터, scheduler 알림 시각마다 발송 · 웹앱 2단계 알림 시간 설정 · check_scheduler·run_daily --fake·check_deliver 통과

- 2026-09-15 · deliver.send_single(메일 한 통), MAIL_FAKE_DIR이면 폴더로 쓰는 검수용 발송기 · 로그인 링크 메일과 웹 검수 · check_auth 통과

- 2026-09-15 · run_daily --date(검수용 날짜), scheduler 시작 로그에 예열 시각, 앱 로그 UTF-8(로그온 작업이 cmd 리다이렉트로 띄움, 저장소 밖 start_app.cmd) · 세션 7 결정 7·9, 검증 실행을 실제 날짜 기억과 섞지 않으려고 · app.log UTF-8 엄격 디코딩 성공, run_daily --fake 통과

- 2026-09-15 · scheduler 06:55 로컬 모델 예열, 하루 실행 보고에 429 받은 횟수(rate_limits_429) · 세션 7 결정 2·3 · check_scheduler 12항목 통과

- 2026-09-15 · 검증 노드 두 단계(요약 문장 끝에서 자르기, 빈 값·남은 문제는 1회 자가 수정 후 제외), 재시도 결과 반려는 반려로 기록, 하루 실행 보고에 자른 요약(fixed) · 세션 7 결정 1 · run_daily --fake 통과(긴 요약·빈 요약·관련도 2 검사 포함)

- 2026-09-15 · 개발 모드 메일 제목을 [개발 모드 · 프로필 역할]로 변경, 개발 프로필 C(AI 에이전트를 공부하는 개발자) 추가(db.py) · 메일이 가짜 프로필 기준이라 본인 기준 브리핑 요청, A·B·C 모두 받기로 결정 · check_deliver·run_daily --fake·check_tables 통과

- 2026-09-15 · 코드 변경 없음, 첫 실제 메일 발송 · 9/15 브리핑(사용자 1·카드 5)을 개발 모드로 ADMIN_EMAILS에 Gmail SMTP 발송 · 사용자 받은편지함 도착 확인, sent_at 5행

- 2026-09-15 · scheduler.py 추가(07:00 실행·08:00 발송·따라잡기·발송 재시도), deliver.py를 Gmail SMTP 직접 발송으로 변경(개발 모드는 ADMIN_EMAILS로), persist.users_with_briefings · n8n 제외·앱 안 예약·개발 모드 본인 발송 예외(사용자 결정) · check_scheduler 11항목, check_deliver 24항목 통과

- 2026-09-15 · deliver 발송함에 보내는 사람(GMAIL_USER) 추가 · n8n 2.x는 식에서 환경변수를 막아 앱이 담아 준다 · check_deliver·check_workflows 통과

- 2026-09-15 · briefing_mail.py·deliver.py 추가, 전량 하루 실행 1회 · 08:00 발송(멱등)과 세션 4 다음 시작점 · check_deliver 19항목 통과, 전량 실행 통과(2명·카드 7·반려 5·호출 23·650초), 9/14 브리핑 개발 모드 콘솔 발송 2통·sent_at 7행

- 2026-09-14 · collect_items 실패 소스 필드 수정, 첫 실제 하루 실행(--users 1 --limit 40) · 로컬 모델 전환 뒤 첫 실행 · 통과(카드 3·반려 0·제외 0, 호출 8회 ollama gemma3 4·groq qwen3.8 4, 토큰 입력 22,963·출력 4,567, 486초, 형식 실패 2회 모두 재시도 복구), MCP 레지스트리 ReadTimeout으로 도구 0건

- 2026-09-14 · run_daily --users·--limit, 모델 장애 사용자·카드 건너뜀·전원 실패 종료 코드 2, 카드 0건 empty_reason 행 저장, 형식 실패 예시 파일 누적, 사용한 제공자 보고 · 로컬 모델 전환과 세션 3 결정 반영(세션 4) · run_daily --fake 29항목 통과

- 2026-09-14 · validate.py·persist.py·run_daily.py 추가, items.source_tier 저장 연결 · 계획안 부록 B 5·6, 세션 3 목표(첫 브리핑 DB 저장). 한글 비율은 글자 기준이면 제품명 많은 정상 요약이 54%로 떨어져 어절 기준으로 정함 · run_daily --fake 21항목 통과(Supabase 실제 저장·재실행 멱등·발송 사용자 건너뜀), 실제 모델 실행은 한도 초기화 후

- 2026-09-14 · dedupe SOURCE_TIER에서 벤처비트 제거, README 할 일에 필터 후 건수 반영 · 벤처비트 소스 제외 결정 · check_folder_docs 통과
- 2026-09-13 · normalize.py, dedupe.py 구현, MCP는 이름으로 중복 판단하도록 수정 · 착수 9번, 레지스트리 서버들이 같은 링크를 공유해 오병합 발견 · run_dedupe 통과(7항목), 2,233 → 2,227건
- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
