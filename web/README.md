# web/

프레임워크 없는 정적 HTML·JS 웹앱. 화면 모양 기준은 `docs/design-reference.html`. PWA 설치 가능.
## 파일
- `app.js`: 공통 도우미 `TS` (API 호출·401이면 /login·이스케이프·앱 셸). `TS.shell`(로그인 화면)·`TS.bare`(세션 없는 화면) 공통 푸터 `TS.footer()`(운영정책·이용약관·개인정보처리방침 굵게·고객센터 문의하기·© 2026 toolscout)는 `TS.frame`이 붙여서 두 셸 화면 모두 맨 아래에 나온다
- `login.html`: 첫 화면(dawn 그림 `.ill-lg` 240×180·폰 120×90 → "개발자를 위한 매일 아침 8시 AI 브리핑" + 실물 검증 줄·3단계·예시 카드 2장, 오른쪽 로그인·구글·가입·예시 보기). 검증 줄 글은 예시 도구 카드 판정 글(`.verdict > span`)과 설치 명령을 인라인 script가 그대로 복사한다(못 불러오면 같은 고정 글). 상단바는 `TS.bare({ tagline: true })` / `signup.html`: 위 단계 표시 + 지금 단계 입력만(상단바 tagline 켬) / `pending.html`: 승인 대기(그림 #pending·다음 일 3줄)
- `index.html`: 오늘 브리핑. 본문 한 열(제호 마크 40px+날짜 36 → 둘째 줄 '새 MCP·스킬 n개 · MCP 설치 확인 a/b' + '어떻게 골랐나' 글자 단추 → 메일 상태·기준 → 이중 괘선 → 큰 소식(리드) → 뉴스 → 새 MCP·스킬 → 다 봤어요·AI 고지) + 1200 이상 오른쪽 레일(도구 줄 목록 → 주제로 거르기 → 질문 → 오늘 한눈에, 자체 스크롤 없음, 높이 760 이상일 때만 sticky). 1199 이하는 제호 → 칩 줄 → 도구 줄 목록 → 카드. 빈 상태: 아직 없음 = dawn 그림, 카드 0장 = empty 그림. 질문은 `ask.js`(`?ask=1`이면 바로 열림)
- `cards.js`: 카드 겉면(머리줄[꼭지 글 | 판정 배지 `Cards.badge`] → 제목 → 메타('3일 전 등록') → 요약 → 나에게 → 판정 한 줄/2×2 → 고정 문구 → $ 설치 명령 → 버튼 줄), 자세히(장단점·검증 세부·왜 이 카드), 세 무게(리드·둘째 큰 소식·뉴스 `.nw`는 상자 없음, 도구만 상자), `Cards.mount`(한 열 배치·다 봤어요·레일 `#toc`·`#tool-rows`), `Cards.today`(마스트헤드, 펼침은 rule-2 위), `Cards.toolHead`·`Cards.counts`(도구 머리 셈, 메일 `verification.tool_head`와 같은 규칙), `Cards.toolRows`(도구 줄 목록), `Cards.empty`(빈 상태 상자). 배지 낱말·도구 머리 글은 `tests/web/verdict_cases.json`과 같다
- `settings.html`: 설정(구역 id `#about #topics #delivery #make #account`, 저장 바, 맨 아래 '되돌릴 수 없는 일') / `onboarding.html`: 첫 설정 4단계(n/4 표시, 4단계 그림 #done) / `profile.js`·`profile.css`: 두 화면이 같이 쓰는 직군 칩·슬라이더·도구 태그 입력
- `f.html`: 메일 버튼 링크 결과(48px 상태 아이콘: 기록 ok·지움 na·이미 info·만료 wait·실패 bad), 이상함이면 사유 3택, 웹에서 이 카드 열기 / `policy.html`: 운영정책 / `support.html`: 고객센터 문의 폼(로그인 없이 가능, 로그인하면 이메일 미리 채움) / `privacy.html`·`terms.html`: 방침·약관
- `manifest.json`, `icons/`: PWA(any maskable 192·512, apple-touch 180)와 마크 원본 `mark.svg`·파비콘 `icon.svg` / `img/illus.svg`: 빈·대기·끝·아침(`#dawn`, '곧 와요' 상태) 그림 symbol 4개 / `img/mail/`: 메일 PNG. PNG는 루트 `bake_icons.py`가 굽는다
- `admin.html`: 관리자 가입 승인(맨 위 승인 대기 크게·방금 처리 되돌리기, Gmail은 못 보낼 때만 경고 띠, 변경 이력 접힘, 사용자 표에 마지막 로그인·마지막 결정, 제자리 상태 확인 줄) 맨 아래 "문의" 구역(최근 문의·처리함 버튼, 승인 배지에는 안 넣음). cards.css를 읽지 않는다(구역 머리 `.lane-h`·상태 칩 `.fchip`만 자체 `<style>`에, 2라운드). 줄 수를 늘리지 않는다
- `privacy.html`·`terms.html`: 로그인 없이 읽는 개인정보처리방침·이용약관(`/privacy`·`/terms`, login·signup 아래에 링크) / `demo.html`: 공개 데모(`demo_sample.json` 고정 예시). 같은 카드 템플릿을 `Cards.readonly`로 버튼 없이, 마스트헤드에 예시 안내와 회원가입·로그인 링크
- `history.html`: 지난 브리핑. 왼쪽 날짜 목록(월별)+오른쪽 그날 판(머리는 오늘과 같은 `Cards.today`, 이전·다음 단추는 날짜 위), 이름 검색은 날짜별 묶음, 모바일은 목록 → 그날 두 화면

## 새 공통 체계 (2026-10-09)
- `app.css`: 토큰(라이트·자동 다크·수동 다크, 2차 리디자인 중립 팔레트·크기·간격·겹침)·앱 셸·공통 컴포넌트·판정 배지 `.pill-*`·그림 `.ill`(login dawn은 `.ill-lg` 240×180)·워드마크 옆 설명 `.tagline` / `cards.css`: 카드·보드·마스트헤드·빈 상태(카드 화면 index·demo·history·login head가 직접 링크) / `home.css`: 오늘·예시 화면 배치(본문+레일·도구 줄 목록·주제 거르기·구역 이동 칩, index·demo만 링크. 화면당 CSS 예산 minify 42KB·gzip 10KB 때문에 cards.css에서 나눔) / `ask.js`: 질문 시트 / 앱 셸 `TS.shell({active, ask})`(로그인 화면, 마크·"질문하기 · N회 남음"), `TS.bare({actions, ctabar, tagline})`(세션 없는 화면, tagline은 login·signup·demo만). 아이콘은 Lucide 1.57.0(`docs/asset-licenses.md`)

## 들어오고 나가는 데이터
- 들어옴: `/api/` JSON 응답 (세션 쿠키)
- 나감: 로그인·프로필·피드백·질문 요청 (JSON)

## 관련
- `routes/pages.py`: 화면 라우팅, 루트 `main.py`: `/static`으로 이 폴더를 연다(허용 목록: html·js·css·png·svg·ico·webmanifest·manifest.json만, 나머지는 404)
- 외부 텍스트(기사 제목·요약·모델 답)는 `TS.esc`로 이스케이프, 링크는 http(s)만
- 보호(2026-10-09): 모든 .js·.css 첫 줄에 `/*!` 저작권·AI 이용 금지 고지, 각 .html head에 같은 뜻 주석과 `tdm-reservation` meta. 새 파일에도 넣는다. 배포 때만 루트 `minify_web.py`로 줄인다 2차: login·signup·demo·index·history·settings 끝에 보이지 않는 함정 링크 `/archive/full-index`(aria-hidden, tabindex -1, 화면 밖. 메일에는 넣지 않음)

## 할 일
- [ ] 받아 보는 시각 고르기(알림 시각): 추후 추가. 지금은 '매일 아침 08:00' 고정 문구, 서버 칸 notify_time은 그대로
- [ ] 에이전트 작업 창 SSE (이번 단계 제외)
