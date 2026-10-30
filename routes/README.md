# routes/

웹앱 화면과 기능 API 라우터. 상태: 회원가입·로그인·프로필·브리핑·지난 브리핑·피드백·질문·가입 승인·공개 데모 구현 (계획안 9.3).

## 파일
- `auth.py`: 세션 쿠키(30일)·`/api/me`·로그아웃·`/api/auth/options`, 서명 토큰 로그인 `/auth/verify`(검수·도구용). `require_approved`는 승인된
  사용자만(브리핑·검색·질문·피드백·프로필이 이 검문을 쓰고, 계정 삭제는 세션만) / `signup.py`: 이메일 인증번호 가입·비밀번호 로그인(scrypt, 5번 잠금) / `google.py`: 구글 OAuth(로그인 + 관리자 전용 Gmail 발송 연결 `/admin/gmail/connect`, 같은 콜백에서 state 종류로 가름)
- `invite.py`: 관리자 가입 승인 대기 목록·승인·차단·사용자 목록·변경 이력(`/api/admin/*`, ADMIN_EMAILS만, 상태가 바뀌면 status_changes에 기록). 초대 코드·신청서는 2026-10-08에 뺐다
- `demo.py`: 공개 데모 `/demo`와 `/api/demo/briefing`. `web/demo_sample.json` 고정 예시(가상 회사·제품, DB 없음), IP당 분당 60회 / `support.py`: 고객센터 문의 `POST /api/support`(비로그인, 저장 + 관리자에게만 메일 한 통 + Reply-To, 문의자에게는 자동 메일 없음, 비로그인 1시간 3건·로그인 10건, 꿀단지, 중복 거름)와 관리자 `GET /api/admin/support`·`POST /api/admin/support/{id}/handled`
- `w1.py`: 아침 브리핑 작업을 직접 부르는 API (X-Service-Key). 실행·지금 발송·예약 상태 / `protect.py`: 1차 보호 장치. AI 크롤러 UA 403(robots.txt 제외)·모든 응답에 X-Robots-Tag(noai, noimageai; 데모·로그인 말고는 noindex)·`/static` 허용 목록. 못 막는 것: UA를 속이는 크롤러, 화면을 직접 받아 가는 사람
- `tokens.py`: SESSION_SECRET HMAC 서명 토큰(로그인·세션·피드백 링크), 1회용은 `used_tokens`에 해시로 기록 / `guard.py`: 보호 2차(2026-10-09). 함정 링크 `/archive/full-index`(robots Disallow, 화면에 숨긴 링크, 메일 제외)를 부른 클라이언트(IP+UA의 HMAC만 저장)를 24시간 차단(403, 로그인 세션은 통과), 브리핑·검색·데모 API 요청 수 제한(DB 1분 창, 로그인 분당 120·비로그인 30, 429+Retry-After, DB가 안 되면 통과, RATE_LIMIT_USER·ANON·OFF) / `watermark.py`: 카드 본문 글·메일 끝의 사용자별 0폭 문자 표식과 해독 명령 `python -m routes.watermark "<글>"`(다시 쓰면 사라짐)
- `pages.py`: `/login`(첫 화면) `/signup` `/pending` `/onboarding` `/` `/settings` `/history` `/admin/invites` `/f` 화면과 `/robots.txt`. 세션 없으면 /login, 승인 전이면 /pending, 프로필 없으면 /onboarding(첫 설정), 데모 말고는 noindex `/policy` `/support`(로그인 없이, 색인 허용)
- `settings.py`: 프로필(직군 5·주제 10 관심도·도구·자유 한 줄·알림 채널·시간), 내 기억 지우기, 계정 삭제, 오늘 브리핑 지금 만들기(본인만)
- `briefings.py`: 오늘·날짜별 브리핑(내 카드·피드백 상태·N건 중 M건·기준 한 줄·관리자만 트레이스·카드 item_meta(pipeline/persist.card_extras, 메일과 공용)·run_stats), 날짜 목록, 키워드 검색
- `feedback.py`: 피드백 W3. 웹 세션 버튼·재클릭 취소·사유 3택·메모, 메일 서명 링크(24시간·1회용, /f 화면 스크립트가 기록)
- `ask.py`: 질문창 W2. 한도 → 게이트 → out 고정 응답(답변 모델 미호출·한도 미차감) / in·unclear는 항목 키워드 검색과 의미 검색(`embeddings.py`, 키·표가 없으면 키워드만)(한글 이름은 `agent/term_dict.json`으로 영어 표기를 덧붙임) → 해설가 답
  (fetch_article 3회·600자·후보 링크만 출처). 맥락은 최근 3턴 원문 + 이전 한 줄 요약(out 제외), 연속 out 3회면 예시

## 들어오고 나가는 데이터
- 들어옴: 브라우저 요청(세션 쿠키), 메일 링크(서명 토큰), 관리자 요청(서비스 키)
- 나감: 화면 HTML(`web/`), JSON 응답, 로그인 메일(`pipeline/deliver.send_single`)

## 관련
- 루트 `main.py`: 라우터와 `/static`(web/) mount / `pipeline/`: scheduler·run_daily·deliver
- `tests/web/`: 가입·로그인·피드백·질문 검수 / `tests/access/`: 가입 승인·데모 검수

## 할 일
- [ ] 카카오 로그인 (자리만 비워 둠)
- [ ] 공개 MCP 도구와 에이전트 작업 창 SSE (이번 단계 제외)
- [ ] 질문 답의 레지스트리 조회: `lookup_registry`가 아직 골격이라 지금은 fetch_article(깃허브 등 허용 도메인)만 쓴다
