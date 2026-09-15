# pipeline/ CHANGELOG

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
