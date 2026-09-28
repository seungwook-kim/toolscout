# pipeline/ CHANGELOG

- 2026-09-28 · 개발 모드 묶음 메일([개발 모드] 제목·"가짜·테스트 프로필 N개" 목차) 없앰. 모든 모드에서 사용자마다 한 통, 운영과 같은 제목·모양. 개발 모드의 가짜 테스트 프로필은 ADMIN_EMAILS로 가고 제목 앞에 [테스트 프로필 직군](deliver.addressed), 한 통 실패는 그 사용자만 미발송 · 사용자 "실전으로 갈 거라 메일도 다 수정해" · check_deliver·check_mail_layout 통과

- 2026-09-28 · 감시 작업을 10분마다로 바꾸고 watchdog.ps1(저장소 밖)에 복구 단계: 45초 뒤 재확인, 런처 작업 꺼짐→시작 / 앱 멈춤→프로세스 종료(런처가 재기동) / 런처만 있음→작업 재시작, [recover] 기록 · 9/27 23:57 런처가 Ctrl+C 이벤트(0xC000013A)로 앱과 함께 끝나 00:10에 손으로 발견, 보낸 쪽은 확인 못 함 · 사고 재현(런처 작업 중지·앱 종료) 뒤 감시 스크립트가 57초에 복구, check_watchdog 통과

- 2026-09-27 · presend: 새 버전 카드를 발송 전 검증 맨 앞에(한도 4건에 밀리면 예전 버전 결과가 붙었다). weekly: 설치해 본 수에서 원격 전용(설치 해당없음) 제외 · 로직 점검 · check_tool_updates 13·check_weekly 10 통과, 전체 오프라인 검수 46개 통과(모델·E2B 호출 0)

- 2026-09-27 · weekly.py 추가: 금요일 메일 맨 아래 "이번 주 요약"(7일 합계·큰 소식·많이 받은 뉴스 주제 상위 3·직접 설치해 본 MCP와 성공 수·새 버전 도구). 카드 데이터에서만 모으고 모델을 부르지 않는다. render에 weekly 인자, outbox가 사용자마다 붙임 · 추천 기능 3(따로 메일 대신 금요일 브리핑에, 사용자 "추천대로") · check_weekly 9·check_mail_layout·check_deliver·check_scheduler 통과, 9/25 실데이터 미리보기 카드 46장

- 2026-09-27 · tool_updates.py 추가: 최근 30일 카드로 나간 MCP의 제목 버전과 레지스트리 최신 버전을 비교해 새 버전 카드(이유 "받아 본 도구의 새 버전 (a → b)", 원문은 GitHub 릴리스 페이지)를 사용자당 하루 1장 도구 칸 맨 앞에. 발송 전 검증은 새 버전 카드를 다시 설치. collect_items가 최신 버전 목록도 돌려준다 · 추천 기능 2("써봤음" 기록 0건이라 범위를 받아 본 도구로, 사용자 승인) · check_tool_updates 12·check_mcp_now·run_daily --fake 48 통과, 실측 본인 MCP 21개 중 4개 새 버전

- 2026-09-27 · 되돌림 교체 카드의 이유를 card_why 근거로(교체 사정은 pick_why로 트레이스에만). tests/pipeline/format_failures.json을 git 추적에서 뺌(.gitignore) · 9/27 메일에 "AIHawk 설치 실패 후 … 대체합니다"가 나감. 하루 실행이 이 파일에 쓰면 작업 트리가 바뀌어 자동 재시작이 멈춘다 · check_rollback·check_autorestart·run_daily --fake 48 통과

- 2026-09-27 · promo.py 추가: 책 소개 연재·TechCrunch 자체 행사 홍보(세션·티켓·연사, 실제 발표는 남김)·웨비나 뉴스를 모델에 보내기 전에 빼고 실행 보고에 promo_dropped · 9/23 책 소개·9/26 행사 세션 예고가 뉴스 칸에 나감, 사용자 "걸러" · 9/27 0시 후보 152건에서 6건(Claude Code 판정과 일치)·오탐 0, 저장 뉴스 91건 오탐 0, check_promo·run_daily --fake 48 통과

- 2026-09-26 · presend.py 추가: 스킬 발송 전 판독을 run_daily에서 옮기고(300줄 규칙), MCP 카드도 발송 전 E2B 설치 검증(4건·10분 예산). 검증 메모를 요청 상태대로("다음 날 06:00 검증 예정"·미완료 이유·요청 없으면 "검증 안 함"), 위험 신호 확인 필요 줄에 근거(판독 모델만·규칙 검사만)와 정리한 인용문 · 9/16~9/26 발송분 점검에서 MCP 카드 24장 중 10장이 요청 없이 "검증 예정"으로 나감, "모델:" 표시·마크다운이 그대로 나감 · check_mcp_now 18·check_skill_now·check_rollback·check_verifier·check_mail_layout·check_deliver·run_daily --fake 통과

- 2026-09-25 · autorestart: 신호를 보낸 뒤 20초 안에 정상 종료가 끝나지 않으면 강제 종료(os._exit(3))해 런처가 다시 띄운다 · 9/25 19:58 자동 재시작 때 열린 MCP 연결 때문에 uvicorn이 'Shutting down'에서 멈춰 앱이 약 3분 꺼져 있었다(손으로 프로세스를 끝내 복구). 매일 실행도 MCP 연결을 쓰므로 같은 일이 날 수 있었다 · check_autorestart 16항목(끝나지 않는 연결을 열어 둔 실제 uvicorn이 강제 종료로 빠져나옴, 강제 종료를 끄면 멈추는 것도 확인)·check_scheduler·check_importance·run_daily --fake 통과

- 2026-09-23 · watchdog.py 추가: 앱과 따로 도는 Windows 작업이 08:30·09:30·12:30·18:30(놓치면 켜질 때)에 앱 응답(/api/health)과 알림 시각 30분 지난 대상 사용자(데모 제외)의 오늘 발송(briefings.sent_at)을 보고, 앱 무응답·브리핑 없음·미발송·DB 조회 실패를 나눠 ADMIN_EMAILS에 알린다. 같은 날 같은 문제는 한 번, 못 보냈으면 다음 확인에 다시. README 할 일에서 끝난 '다음 날 자동 실행 확인'을 뺐다 · 앱이 통째로 죽으면 앱이 보내는 실패 알림도 안 나가 하루 이틀 뒤에야 알게 된다 (2026-09-23 사용자 요청) · check_watchdog 14항목(신규) 통과, 작업 스케줄러로 한 번 실행해 정상 종료

- 2026-09-23 · autorestart.py 추가, scheduler 루프가 한 바퀴마다 부른다: main에 추적 파일 수정 없이 새 커밋이 있고, 06:00~09:00이 아니고, 하루 실행·검증·재실행 예약이 없고, 다음 예정 작업까지 10분 넘게 남았으면 SIGINT로 정상 종료해 런처가 10초 뒤 새 코드로 띄운다. git이 없거나 AUTO_RESTART=0이면 꺼짐 · 예약 실행이 앱 안에서 돌아 코드를 고치고 재시작을 빠뜨리면 다음 날 옛 코드로 돌았다(9/21) (2026-09-23 사용자 요청) · check_autorestart 14항목(신규)·check_scheduler·check_skill_now·run_daily --fake 통과

- 2026-09-23 · run_daily.review_skills_now 추가: 카드로 나갈 스킬을 하루 실행 안에서 바로 판독하고 결과를 그날 카드에 붙인다(이미 판독된 것·이번에 안 뽑힌 스킬은 건너뜀, 한 번에 5건, 실패해도 실행 계속, 보고에 skills_reviewed) · 검증이 다음 날 06:00이라 처음 나가는 스킬 카드에는 늘 '판독 예정'만 붙었다. SKILL.md 읽기는 몇 초라 실행 안으로 옮길 수 있고, MCP는 E2B 설치 90초라 그대로 06:00에 남긴다 (2026-09-23 사용자 결정) · check_skill_now 10항목(신규)·run_daily --fake·check_verifier·check_rollback·check_scheduler 통과

- 2026-09-22 · briefing_mail 모양 정리: 어두운 머리(요일 포함), 카드는 종류 칩(뉴스는 출처 도메인)·제목·요약·나한테는 순으로 무게를 줄이고 장점·단점은 +·− 한 줄씩, 근거 링크는 원문과 다를 때만, 버튼은 둥근 칩, trace_id는 옅게. 묶음 메일은 맨 위 머리 하나에 프로필 띠, render가 머리 없는 body를 같이 돌려줘 combine이 쓴다. 색은 웹앱 design-reference 토큰 값 · 사용자가 가독성이 너무 떨어진다고 함. 카드 하나가 화면 한 장을 넘고 모든 줄이 같은 무게였으며, 근거 링크가 전부 원문과 같은 주소로 되풀이됐다 · check_mail_layout 12항목(신규)·check_deliver·run_daily --fake·check_scheduler 통과

- 2026-09-21 · persist.save_catalog upsert에 title 갱신 추가 · 별 수 캐시가 먼저 만든 이름 제목이 선별 통과 뒤에도 그대로 남았다 · check_catalog_title 9항목 통과

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
