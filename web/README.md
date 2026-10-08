# web/

프레임워크 없는 정적 HTML·JS 웹앱. 화면 모양 기준은 `docs/design-reference.html`. PWA 설치 가능.
## 파일
- `app.js`: 공통 도우미 `TS` (API 호출·401이면 /login·이스케이프·앱 셸). 옛 `TS.mast`는 다리
- `login.html`: 첫 화면(이메일·비밀번호 로그인, 회원가입, 구글로 계속하기, 가입 없이 예시 보기) / `signup.html`: 인증번호 받기·확인·비밀번호 / `pending.html`: 승인 대기
- `index.html`: 오늘 브리핑. 마스트헤드(날짜·기준·발송)·파이프라인 3칸, 뉴스/도구, 질문 스레드(.q/.a·확인한 곳 칩)와 하단 고정 입력바
- `cards.js`: 뉴스 .item(주제 색 점)·도구 .tool(종류·별 수·공개 시점·배포 방식·검증 칩 또는 스킬 위험 신호·명령 복사, 고정 문구 두 개), 파이프라인(검증관 칸 검증 수·되돌림 수), 버튼(aria-pressed·muted·서버 문구)
- `settings.html`: 직군 선택, 주제 관심도(접힘·프리셋 자동), 도구·자유 한 줄, 알림 채널·시간, 지금 만들기, 기억 지우기·계정 삭제(확인창)
- `f.html`: 메일 버튼 링크 결과, 이상함이면 사유 3택
- `manifest.json`, `icons/`: PWA
- `admin.html`: 관리자 전용 승인 탭(가입 승인·거절, 가입 상태·가입 방법, 변경 이력). 2026-10-08부터 기능만, 디자인은 목업 확정 뒤 다시
- `demo.html`: 공개 데모(`demo_sample.json` 고정 예시). 같은 카드 템플릿을 `Cards.readonly`로 버튼 없이, 마스트헤드에 예시 안내와 회원가입·로그인 링크
- `history.html`: 지난 브리핑. 날짜마다 접었다 펴는 칸(펼칠 때 그날 카드를 불러옴, 최근 날짜는 펼쳐 둠), 이름 검색(DB LIKE) → 그날 칸 펼치기

## 새 공통 체계 (2026-10-09) 와 남은 옛 다리
- `app.css`: 토큰(라이트·다크)·앱 셸·공통 컴포넌트 / `cards.css`: 카드·보드 / `ask.js`: 질문 시트 / 앱 셸 `TS.shell({active, ask})`(로그인 화면), `TS.bare({actions, ctabar})`(세션 없는 화면)
- 남은 것: 모든 `*.html`이 아직 `TS.mast`(옛 다리)와 `<header class="mast">`를 부른다. 화면을 `TS.shell`·`TS.bare`로 바꾸면 그 화면 body의 `legacy` 클래스가 없어진다. 전부 바꾼 뒤 `TS.mast`, `web/legacy.css`, `app.css` 첫머리의 `@import url("legacy.css")`를 지운다
- legacy.css가 받치는 옛 클래스: `.sec .sec-h .item .acts .act .go .askbar .thread .q .a .refs .board details.day details.why .forme`

## 들어오고 나가는 데이터
- 들어옴: `/api/` JSON 응답 (세션 쿠키)
- 나감: 로그인·프로필·피드백·질문 요청 (JSON)

## 관련
- `routes/pages.py`: 화면 라우팅, 루트 `main.py`: `/static`으로 이 폴더를 연다
- 외부 텍스트(기사 제목·요약·모델 답)는 `TS.esc`로 이스케이프, 링크는 http(s)만

## 할 일
- [ ] 에이전트 작업 창 SSE (이번 단계 제외)
