# web/ CHANGELOG

- 2026-09-26 · cards.js 스킬 위험 신호 인용 앞에 근거(판독 모델만·규칙 검사만 위험으로 봄) · 내부 표시 "모델:"이 그대로 보이던 것 · check_design·check_briefings 통과
- 2026-09-16 · invite.html·admin.html·demo.html 추가, cards.js에 readonly(버튼 없이 카드만) · 초대 코드 화면과 공개 데모 · check_access 통과
- 2026-09-16 · cards.js 파이프라인 검증관 칸을 run_stats verified·verify_requested·rollbacks로 채움("아직 붙지 않았어요" 문구 제거) · 세션 8 5단계 · check_design·check_rules 통과
- 2026-09-15 · cards.js: 스킬 카드 "SKILL.md 읽어봤더니"(위험 신호 칩·충실도·인용), MCP 검증 메모(설치법 미확인 등), 고정 문구(도구 동작은 범위 밖·안전 보증 아님)를 결과가 없어도 표시 · 세션 8 검증관 4단계 · check_design·check_rules 통과
- 2026-09-15 · history.html: 날짜 칩과 그날 칸을 날짜마다 접었다 펴는 details 칸으로(머리는 .sec-h, 처음 펼칠 때 불러옴), app.css 보충에 접힘 삼각형 · 사용자 요청 · check_briefings·check_design 통과
- 2026-09-15 · 화면 전체를 docs/design-reference.html 기준으로(app.css 참고 style 그대로 + 토큰만 쓴 보충, 마스트헤드·파이프라인·.item/.tool·질문 스레드·고정 입력바, 설정·지난 브리핑·로그인·피드백은 같은 마스트헤드와 .sec/.item), PWA manifest·아이콘 · 사용자 디자인 기준 지시 · check_design·tests/web 회귀 통과, 폰 390·PC 1280 가로 넘침 0
- 2026-09-15 · cards.js: related 카드는 "이번 주 관련 MCP·스킬" 칸에 따로 · F3-b 관련 카드 · check_rules·check_briefings 통과
- 2026-09-15 · app.css: "어떻게 만들어졌나" 링크를 카드 흐름 안으로(긴 제목과 겹침) · 웹앱 본체 8단계 스크린샷에서 발견 · 폰 412폭 가로 넘침 0, check_rules 통과
- 2026-09-15 · history.html 추가, cards.js mount에 날짜 문구(오늘/이날) · 웹앱 본체 6단계 지난 브리핑(F8) · check_briefings 12항목 통과
- 2026-09-15 · index.html 질문창: "AI 질문이었어요"가 첫 답에만 붙던 문제 수정, 답 기다리는 동안 버튼 잠금 · 웹앱 본체 5단계 W2 · check_ask 통과
- 2026-09-15 · f.html 추가, cards.js 버튼 동작(재클릭 취소·사유·메모) · 웹앱 본체 4단계 W3 · check_feedback 통과
- 2026-09-15 · index.html 오늘 브리핑으로 교체, cards.js 추가 · 웹앱 본체 3단계 · check_briefings 통과

- 2026-09-15 · settings.html 추가 · 웹앱 본체 2단계 프로필·설정 · check_settings 통과

- 2026-09-15 · app.css·app.js·login.html 추가 · 웹앱 본체 1단계 로그인, 반응형 공통 스타일 · check_auth·check_main 통과

- 2026-09-13 · index.html "toolscout 준비 중" 페이지 작성 · 착수 12번 · check_main 통과
- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
