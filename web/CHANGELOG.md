# web/ CHANGELOG

- 2026-10-09 · login·signup·demo·index·history·settings 끝에 보이지 않는 함정 링크(aria-hidden, tabindex -1, 화면 밖) 추가 · 무단 복제 2차 보호(규칙을 무시하는 봇 잡기) · check_protect2·check_design 통과
- 2026-10-09 · cards.js: GitHub 검색 출처(item_meta.source=github_search) 카드의 종류 옆 표시를 "GitHub"로(레지스트리 공식/커뮤니티 구분은 인증이 있는 레지스트리 항목만) · 읽기 쉬운 출처 이름 · 코드 검토만, 화면 확인은 못 함
- 2026-10-09 · 모든 .js·.css 첫 줄에 `/*!` 저작권·AI 이용 금지 고지, 각 .html head에 같은 뜻 주석과 tdm-reservation meta 추가 · 무단 복제·AI 크롤링 1차 보호 · check_protect·check_rules·check_design 통과
- 2026-10-09 · settings·onboarding 자유 한 줄 200자(입력 칸·글자 수·넘으면 경고), 서버 memory.FREE_TEXT_MAX=200 · 사용자 "자유 한줄 200자로 바꿔줘" · check_settings 통과
- 2026-10-09 · 옛 다리 정리: TS.mast, web/legacy.css, app.css의 legacy 불러오기 삭제(화면 9개 모두 TS.shell·TS.bare로 옮겨짐), admin.html에 남은 `</style>` 하나 지움(CSS가 글자로 보였음), 실제 화면을 라이트·다크 1366px·390px로 찍어 확인 · 리디자인 마무리 · check_design·check_auth·check_settings·check_briefings·check_feedback·check_ask·check_rules 통과
- 2026-10-09 · history·settings·admin·f 화면을 합의 목업대로 새로 만들고 onboarding.html(첫 설정)·profile.js·profile.css(직군 칩·슬라이더·도구 태그, 설정과 공유) 추가, 네 화면은 TS.shell/TS.bare로 옮겨 옛 다리 안 씀, 설정에서 알림 시각 고르기는 뺌(문구 '매일 아침 08:00'), 관리자 사용자 표에 마지막 로그인 · 사용자 결정 '목업대로 실제 화면을 만든다'·'알림 시각은 추후' · check_settings·check_briefings·check_apply·check_feedback·check_auth·check_design 통과
- 2026-10-09 · 공통 디자인 체계 새로 씀: app.css(토큰 라이트·다크, 앱바·탭·하단 탭·버튼·입력·알림·알약·저장 바·확인 줄), app.js(TS.shell·TS.bare·TS.confirmLine·TS.setPending), cards.js·cards.css(카드 해부도, 자세히, 관리자 트레이스, 관심없음 접기), ask.js(질문 시트), legacy.css(옛 화면 다리) · 리디자인 1·2차 회의 합의 · check_design 통과. 화면 9개는 아직 TS.mast(다리)를 부른다
- 2026-10-08 · signup.html에서 구글 가입·예시 보기 링크를 빼고 위에 로그인으로 돌아가기 링크 하나만 · 사용자 "다른길 유도는 필요 없을 듯"(구글은 첫 화면에서만) · check_auth·check_design 통과
- 2026-10-08 · login.html 첫 화면(로그인·회원가입·구글·예시 보기), signup.html·pending.html(신규), invite.html 삭제, admin.html 초대 코드 칸 제거, demo_sample.json(가상 예시)·demo.html 예시 안내 · 사용자 결정 "회원가입 버튼 + 구글 로그인, 가입 안 하면 가짜 뉴스 데모", 디자인은 전문가 회의 목업 뒤 다시 · check_auth·check_access 통과
- 2026-10-04 · cards.js 검증 칩 색 표에 서버 값 bad를 더함 · 실패(bad)가 표에 없어 설치·실행 실패가 회색(해당없음 색)으로 보였다 · check_probe_labels 통과
- 2026-09-28 · admin.html에 변경 이력 칸(이전 → 새 상태·누가·언제)과 사용자마다 마지막 결정 · 승인 이력 · check_apply·check_design 통과
- 2026-09-27 · invite.html에 이용 신청서(이름·하는 일·이유·알게 된 곳·동의, 낸 뒤 상태·고치기), admin.html 맨 위에 이용 신청 목록(승인·거절, 신청 글 이스케이프), app.js 메뉴에 관리자만 "승인 N" 탭, app.css textarea(토큰만) · 사용자 요청 · check_apply·check_design·check_access 통과
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
