# docs/ CHANGELOG

- 2026-10-15 · design-reference.html --line 견본 #C4C6BF, --hl-border 줄 삭제, --fs-4xl·TS.bare tagline·#dawn 견본 추가, asset-licenses.md에 #dawn(자체 제작) · 디자인 회의 2라운드 덩이 0(견본이 app.css와 같아야 함) · check_rules 통과
- 2026-10-14 · design-reference.html을 2차 리디자인 토큰·마크·판정 배지·그림 견본으로 갱신(cards.css 직접 링크), asset-licenses.md·licenses/lucide.txt 신규 · Lucide·글꼴 라이선스 기록과 새 디자인 기준 · check_rules(app.css 링크) 통과
- 2026-10-11 · deploy.md 남은 일: 임시 비밀번호 123456을 지운 기록(계정 45·1·2·3·113, 운영 로그인 400 확인)과 관리자 로그인 방법 · 사용자 "응 진행해"(디자인·기능이 끝나면 지우기로 한 것) · check_folder_docs 통과
- 2026-10-11 · deploy.md 운영 모델(Haiku 5.5 + gpt-4o-mini 대체)과 ANTHROPIC_API_KEY(Railway·Vercel) 안내 · 모델 전환 결정 반영 · 문서 검수 통과
- 2026-10-09 · deploy.md: Railway 설정 절(railway.json이 안 먹어 IaC로 적용, 싱가포르, 크론 일정·재시작 안 함, 적용 방법), 예외용 무료 대안 GitHub Actions 절 · 사용자 "GitHub Actions 이건 예외로 사용할 수 있고 무료이다 라고 명시해놔, 레일웨이로 간다" · check_folder_docs 통과
- 2026-10-09 · deploy.md에 "Gmail API로 메일 보내기" 절(Railway 환경변수·연결 순서·구글 콘솔 설정) · Railway Hobby가 바깥 SMTP를 막아서 · 문서 검수 통과
- 2026-10-09 · deploy.md에 "보호 장치 2차" 절(환경변수·운영 확인 방법·개인정보 메모·머지 때 할 일) · 무단 복제 2차 보호 · check_folder_docs 통과
- 2026-10-09 · deploy.md 올리는 방법에 화면 경량화 단계(minify_web.py)와 보호 장치 설명 추가 · 무단 복제·AI 크롤링 1차 보호 · check_folder_docs 통과
- 2026-10-09 · 리디자인 마무리 검수(문서 규칙·README 폴더 문서 점검) · 새 공통 체계 반영 · check_folder_docs·check_readme 통과
- 2026-10-09 · design-reference.html을 새 공통 체계 견본으로 다시 씀(app.css 링크, 배치만 자체 style) · 리디자인 회의 합의 · check_design 통과
- 2026-10-07 · deploy.md(신규): Vercel 웹 + Railway 크론 구조·환경변수·올리는 방법·넘어가기, README에 줄 추가 · 사용자 결정 "vercel + railway", 서버 모델 "mini-4o" · check_folder_docs 통과
- 2026-10-05 · README의 local-model.md 설명에 "모델표에서 뺌, 기록용" · 사용자 결정으로 개발 모드 모델표에서 Ollama를 뺌(models.py) · check_folder_docs 통과
- 2026-09-16 · 계획안 6장 범위에 초대제 가입과 읽기 전용 데모 /demo 추가 · 2026-09-16 사용자 결정 반영 · check_folder_docs·check_readme 통과
- 2026-09-15 · 계획안 9.5에 verify_requests 표, probes·skill_reviews 칸(skipped 포함) · 세션 8 검증관 · check_readme 통과

- 2026-09-15 · design-reference.html(웹앱 디자인 기준) 추가, img에 today-desktop·today-mobile·pwa-standalone · 사용자 디자인 지시 · check_readme 통과

- 2026-09-15 · 계획안 9.3 카드 JSON에 related(월요일 관련 카드) · W4-d F3-b 구현과 규격 일치 · check_readme 통과

- 2026-09-15 · 계획안 5장 합치기 행: 피드백으로 바뀐 만큼 되돌려 직군 프리셋(설정에서 고친 값) 기준으로 · W4-c 구현과 문구 일치 · check_readme 통과

- 2026-09-15 · 계획안: 합치기는 30일 무반응 주제를 직군 프리셋 값으로, F3-b 후보는 선별 통과 도구를 items에 쌓은 목록·월요일 최대 3장, items에 description · 사용자 결정 3개(W4-b 착수 전 질문) · check_readme 통과

- 2026-09-15 · 계획안 부록 B 예외 표에 하루 실행 실패 재실행(30분·2번)·실패 알림 행 · W4-a 구현과 문서 일치 · check_readme 통과

- 2026-09-15 · img/에 웹앱 스크린샷 3장(PC 오늘 브리핑 web_cards.png, 폰 오늘·지난 브리핑) · 웹앱 본체 8단계, 본인 계정 로그인 뒤 실제 브리핑(카드 6)과 질문 1개 · check_readme 통과

- 2026-09-15 · 계획안 9.5 데이터 표에 used_tokens · 로그인·메일 피드백 링크 1회용 기록 · check_tables 표 10개 통과

- 2026-09-15 · 계획안: 부록 B 4에 관련도 3 미만 반려, 부록 B 5에 검증 노드 두 단계, 예외 표에 MCP 레지스트리 수집 실패·모델 429, 9.2와 자동화 표에 "개발 중 앱 내 스케줄러, 배포 시 n8n 크론이 /api/w1/run 호출", 9.3 카드 규격에 relevance · 세션 7 결정 1·3·4·6·9 · check_readme 통과

- 2026-09-15 · local-model.md 선택표(해설가 groq → gemma3 대체)와 주의(06:55 예열, 로컬 첫 호출 90초) · 세션 7 결정 2·3 · check_models 통과

- 2026-09-15 · 계획안에서 n8n 제거(자동화 표·흐름도·9.2 예약 작업·알림 SMTP·배포 1컨테이너·부록 F), 개발 모드 본인 발송 예외 기록 · 사용자 결정(n8n 제외, 앱 안 예약) · check_readme 부록F 동일 확인

- 2026-09-15 · 부록 F pipeline 줄에 deliver.py·briefing_mail.py 추가 · 08:00 발송 파일 반영 · check_readme 부록F 동일 확인

- 2026-09-14 · local-model.md 추가(VRAM·도구 호출·한글 실측표, gemma3:12b 선택), 계획안 예외 표에 모델 장애 행·빈 행 저장, 부록 B 5에 한글 비율 어절 60% 명시, 부록 F docs 줄 · 로컬 모델 전환과 세션 3 결정 반영(세션 4) · check_local_models 4개 측정, check_readme 부록F 동일 확인

- 2026-09-14 · 계획안 끝에 부록 F. 디렉토리 구조 추가 (루트 README 트리와 동일, config.py·.github 반영) · 작업 규칙의 구조 기준이 부록 A에 없어서 · check_readme 부록F 동일 검사 통과
- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 루트 계획안 원본을 docs/계획안.md로 이동 · 작업 규칙이 이 경로를 기준으로 삼음 · 검수 없음
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
