# docs/

설계 문서와 이미지. 상태: 계획안, 로컬 모델 실측, 웹앱 화면 스크린샷.

## 파일
- `계획안.md`: 전체 설계의 유일한 기준 (v3.2). 작업 규칙과 충돌하면 이 문서가 이긴다. 폴더 구조는 부록 F
- `design-reference.html`: 웹앱 디자인의 유일한 기준(토큰·마크업 구조). `web/app.css` 앞부분이 이 파일 style 그대로
- `local-model.md`: 개발용 로컬 모델(Ollama) VRAM·도구 호출·한글 실측표와 선택 근거(2026-10-05부터 모델표에서 뺌, 기록용). 모델 배정 자체는 루트 `models.py`
- `img/`: 스크린샷. `today-desktop.png`·`today-mobile.png`(디자인 기준 적용), `pwa-standalone.png`, 예전 `web_cards.png` 등

## 들어오고 나가는 데이터
- 들어옴: 설계 변경 결정
- 나감: 모든 폴더 작업의 기준

## 관련
- 루트 `README.md`: 계획안을 줄여 소개한다. "프로젝트 구조" 트리는 부록 F와 같아야 한다 (`tests/docs/check_readme.py`)

## 할 일
- [ ] 스크린샷 나머지 3장: 에이전트 작업 창, Langfuse 트레이스, Claude Code에서 ask_briefing