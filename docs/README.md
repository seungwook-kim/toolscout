# docs/

설계 문서와 이미지. 상태: 계획안, 로컬 모델 실측, 웹앱 화면 스크린샷.

## 파일
- `계획안.md`: 전체 설계의 유일한 기준 (v3.2). 작업 규칙과 충돌하면 이 문서가 이긴다. 폴더 구조는 부록 F
- `design-reference.html`: 웹앱 디자인의 유일한 기준(토큰·컴포넌트 견본, 판정 배지·그림·마크). 견본은 실제 `web/app.css`·`cards.css`·`app.js`를 불러와 그린다
- `asset-licenses.md`: 외부 자산(Lucide 아이콘, Pretendard·JetBrains Mono 글꼴)과 자체 제작 그림의 출처·라이선스·가공 / `licenses/lucide.txt`: Lucide 고지 전문
- `local-model.md`: 개발용 로컬 모델(Ollama) VRAM·도구 호출·한글 실측표와 선택 근거(2026-10-05부터 모델표에서 뺌, 기록용). 모델 배정 자체는 루트 `models.py`
- `deploy.md`: 배포 구조(Vercel 웹 + Railway 크론, 2026-10-07), 플랫폼별 환경변수, git에 올린 파일만 내보내 올리는 방법, 첫 점검·이 PC 앱에서 넘어가기
- `img/`: 스크린샷(2026-10-15 2차 리디자인 뒤). 오늘 PC `web_cards.png`(라이트)·`today-desktop.png`(다크), 폰 `web_today_phone.png`·`today-mobile.png`, `web_history_phone.png`, `web_login.png`, 메일 `mail_morning.png`, 앱 설치 모드(display-mode standalone) 폰 `pwa-standalone.png`

## 들어오고 나가는 데이터
- 들어옴: 설계 변경 결정
- 나감: 모든 폴더 작업의 기준

## 관련
- 루트 `README.md`: 계획안을 줄여 소개한다. "프로젝트 구조" 트리는 부록 F와 같아야 한다 (`tests/docs/check_readme.py`)

## 할 일
- [ ] 에이전트 작업 창·공개 MCP(ask_briefing)를 만들면 그 화면 스크린샷을 더한다(지금은 기능이 없어 README 표에서 뺐다)