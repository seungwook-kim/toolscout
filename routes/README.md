# routes/

웹앱 화면과 기능 API 라우터. 상태: 로그인·프로필·브리핑·피드백·질문 API 구현, 지난 브리핑 화면 진행 중 (계획안 9.3).

## 파일
- `auth.py`: 이메일 매직링크 로그인(15분·1회용), 세션 쿠키(30일), `/api/me`. 개발 모드는 ADMIN_EMAILS만 링크 받음, 로그인 사용자 is_test
- `tokens.py`: SESSION_SECRET HMAC 서명 토큰(로그인·세션·피드백 링크), 1회용은 `used_tokens`에 해시로 기록
- `pages.py`: `/` `/login` `/settings` `/history` `/f` 정적 화면. 세션 없으면 /login, 프로필 없으면 /settings
- `w1.py`: 아침 브리핑 작업을 직접 부르는 API (X-Service-Key). 실행·지금 발송·예약 상태
- `settings.py`: 프로필(직군 5·주제 10 관심도·도구·자유 한 줄·알림 채널·시간), 내 기억 지우기, 계정 삭제, 오늘 브리핑 지금 만들기(본인만)
- `briefings.py`: 오늘·날짜별 브리핑(내 카드·피드백 상태·N건 중 M건·기준 한 줄·관리자만 트레이스), 날짜 목록, 내 브리핑 항목 키워드 검색
- `feedback.py`: 피드백 W3. 웹 세션 버튼·재클릭 취소·사유 3택·메모, 메일 서명 링크(24시간·1회용, /f 화면 스크립트가 기록)
- `ask.py`: 질문창 W2. 한도 → 게이트 → out 고정 응답(답변 모델 미호출·한도 미차감) / in·unclear는 항목 키워드 검색 → 해설가 답
  (fetch_article 3회·600자·후보 링크만 출처). 맥락은 최근 3턴 원문 + 이전 한 줄 요약(out 제외), 연속 out 3회면 예시

## 들어오고 나가는 데이터
- 들어옴: 브라우저 요청(세션 쿠키), 메일 링크(서명 토큰), 관리자 요청(서비스 키)
- 나감: 화면 HTML(`web/`), JSON 응답, 로그인 메일(`pipeline/deliver.send_single`)

## 관련
- 루트 `main.py`: 라우터와 `/static`(web/) mount / `pipeline/`: scheduler·run_daily·deliver
- `tests/web/`: 로그인·피드백·질문 검수

## 할 일
- [ ] 카카오 로그인 (자리만 비워 둠)
- [ ] 공개 MCP 도구와 에이전트 작업 창 SSE (이번 단계 제외)
- [ ] 질문 답의 레지스트리 조회: `lookup_registry`가 아직 골격이라 지금은 fetch_article(깃허브 등 허용 도메인)만 쓴다
