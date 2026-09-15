# routes/ CHANGELOG

- 2026-09-15 · settings.py 추가(프로필·기억 지우기·계정 삭제·지금 만들기) · 웹앱 본체 2단계 · check_settings 10항목 통과

- 2026-09-15 · auth.py(매직링크 로그인·세션), tokens.py(서명 토큰·1회용), pages.py(화면 라우팅) 추가 · 웹앱 본체 1단계 로그인 · check_auth 15항목 통과 (1회용 판정을 rowcount로 하던 버그를 RETURNING으로 수정)

- 2026-09-15 · w1.py를 수동 실행·발송·상태 API로 변경(발송함·발송 기록 API 삭제) · n8n 제외, 예약은 앱 안에서 · check_deliver API 2항목 통과

- 2026-09-15 · w1.py 추가(하루 실행 시작·상태·발송함·발송 기록), main.py에 연결 · n8n W1이 앱을 부르는 경로 · check_deliver API 4항목 통과(키 없으면 401·발송함 2통·발송 기록 멱등·상태)

- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
