# pipeline/

수집부터 발송까지 하루 실행 순서와 앱 안 예약. 상태: 구현 (계획안 9.2 W1, 부록 B 1~6).

## 파일
- `normalize.py`: HTML·엔티티 제거, 공백 정리, URL 정규화 / `dedupe.py`: 링크(MCP는 이름) 중복 제거, 뉴스 제목 유사도 0.85 묶기
- `validate.py`: 검증 노드 두 단계. 1) 요약 120자 초과는 문장 끝에서 자름 2) 빈 값·규격·근거 링크·한글 비율(어절 60%)·관련도 문제는 이유를 돌려 1회 자가 수정, 또 실패면 제외·트레이스
- `persist.py`: 통과 카드를 items·briefings(trace_id, sent_at null)·seen에 저장. 카드 0건이면 empty_reason 행. 발송한 사용자는 건너뜀. `save_catalog` 선별 통과 MCP·스킬을 items에 쌓기(주제·원문 설명), `wake_db` DB 깨우기
- `run_daily.py`: 수집 → 정리 → 중복 제거 → 큐레이터 → 도구 목록 쌓기 → 해설가 → 검증 노드 → 저장. 개발 모드는 is_test만, 실행 전체가 트레이스 하나
  - `--users N`·`--limit N`(디버깅 `--users 1 --limit 40`). 모델 장애는 사용자·카드 단위로 건너뛰고 전원 실패면 종료 코드 2
  - 개발 모드 형식 실패 예시는 `tests/pipeline/format_failures.json`에 쌓는다
- `briefing_mail.py`: 메일 본문(HTML·텍스트). 카드 전체·trace_id·피드백 버튼 서명 링크(뉴스 2·도구 3), 뉴스/도구 칸, 빈 행 문구
- `deliver.py`: 미발송 briefings를 사용자별 메일로 Gmail SMTP 발송, 한 통마다 sent_at. 개발 모드는 받는 사람을 ADMIN_EMAILS로 바꾸고
  제목에 [개발 모드], ADMIN_EMAILS가 없으면 콘솔·DB만. 메일 설정이 없으면 기록하지 않는다. `send_alert`: ADMIN_EMAILS 실패 알림(오류 종류만)
- `scheduler.py`: 앱이 떠 있는 동안 06:55 예열·DB 깨우기, 07:00 하루 실행, 알림 시각(08·09·12·18시)마다 발송 (KST). 놓친 실행은 22:00 전에 따라잡음
  실행 실패·빠진 사용자는 30분 뒤 그 사용자만 2번 더, 발송 실패는 10분 간격 2번 더, 끝내 실패하면 실패 알림 한 통(W4)

## 들어오고 나가는 데이터
- 들어옴: `sources/` 항목, 루트 `memory.py` 기억, `agent/` 카드
- 나감: Supabase items·briefings·seen, 실행 보고(건수·토큰·시간·trace_id), 아침 메일

## 관련
- `agent/`: 큐레이터·해설가 / 루트 `main.py`: 예약 시작, `mcp_server.py`: 해설가 원문 재조회(앱 8000 포트) / `routes/w1.py`: 수동 실행·발송·상태
- `tests/pipeline/`: run_dedupe, run_daily, check_deliver, check_scheduler

## 할 일
- [ ] 다음 날 07:00·08:00 자동 실행 확인. 앱은 로그온 작업 `toolscout app` → `%LOCALAPPDATA%\toolscout\start_app.ps1`(uvicorn이 꺼지면 10초 뒤 다시)로 뜬다(로그 UTF-8 `app.log`)
- [ ] 한국어·영어 같은 소식 묶기 (제목 유사도로는 안 잡힘, 큐레이터 단계에서 판단할지 결정)
- [ ] W4 나머지: 주간 기억 합치기(월), F3-b 관련 카드(월), 미완료 검증 재실행(밤, 검증관 뒤), 마감 리마인드
