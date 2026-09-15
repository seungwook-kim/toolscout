# routes/

웹앱 화면과 기능 API 라우터. 상태: 로그인·화면·아침 브리핑 작업 API 구현, 프로필·브리핑·피드백·질문은 진행 중 (계획안 9.3).

## 파일
- `auth.py`: 이메일 매직링크 로그인(15분·1회용), 세션 쿠키(30일), `/api/me`. 개발 모드는 ADMIN_EMAILS만 링크 받음, 로그인 사용자 is_test
- `tokens.py`: SESSION_SECRET HMAC 서명 토큰(로그인·세션·피드백 링크), 1회용은 `used_tokens`에 해시로 기록
- `pages.py`: `/` `/login` `/settings` `/history` `/f` 정적 화면. 세션 없으면 /login, 프로필 없으면 /settings
- `w1.py`: 아침 브리핑 작업을 직접 부르는 API (X-Service-Key). 실행·지금 발송·예약 상태
- 프로필·브리핑·피드백(W3)·질문(W2) API (진행 중)

## 들어오고 나가는 데이터
- 들어옴: 브라우저 요청(세션 쿠키), 메일 링크(서명 토큰), 관리자 요청(서비스 키)
- 나감: 화면 HTML(`web/`), JSON 응답, 로그인 메일(`pipeline/deliver.send_single`)

## 관련
- 루트 `main.py`: 라우터와 `/static`(web/) mount / `pipeline/`: scheduler·run_daily·deliver
- `tests/web/`: 로그인·피드백·질문 검수

## 할 일
- [ ] 카카오 로그인 (자리만 비워 둠)
- [ ] 관리자 카드 → Langfuse 트레이스 링크 (오늘 브리핑 단계)
- [ ] 공개 MCP 도구와 에이전트 작업 창 SSE (이번 단계 제외)
