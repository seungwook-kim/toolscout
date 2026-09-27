# pipeline/

수집부터 발송까지 하루 실행 순서와 앱 안 예약. 상태: 구현 (계획안 9.2 W1, 부록 B 1~6).
`normalize.py`(HTML 제거·URL 정규화), `dedupe.py`(링크·MCP 이름 중복, 제목 유사도 0.85), `promo.py`(책 연재·행사 홍보 뉴스 빼기)가 맨 앞 단계.

## 파일
- `verification.py`: 검증 요청 큐 verify_requests(저장·전날 대기+미완료 재시도·상태), skill_reviews 저장, 카드 칸(verification 칩·risk_signal·요청 상태 메모)
- `rollback.py`: 되돌림 1(검증 실패 도구 → 큐레이터 대체·비움, 항목당 1회) / 2(근거 없는 도구 카드 → 재검증 1회 → 다시 해설, 아니면 "확인 필요", 실행당 5건) / `attach`
- `validate.py`: 검증 노드 두 단계. 1) 요약 120자 초과는 문장 끝에서 자름 2) 빈 값·규격·근거 링크·한글 비율(어절 60%)·관련도 문제는 이유를 돌려 1회 자가 수정, 또 실패면 제외·트레이스
- `persist.py`: 통과 카드를 items·briefings(trace_id, sent_at null)·seen에 저장. 카드 0건이면 empty_reason 행. 발송한 사용자는 건너뜀, 사용자별 run_stats·items.published_at도 저장. `save_catalog` 선별 통과 MCP·스킬 쌓기, `related_pool` 관련 카드 후보 100건(태그·써봤음 이름 일치 > 가중치 > 별 수), `wake_db`
- `presend.py`: 발송 전 검증. 카드로 나갈 스킬은 그 자리 판독(5건), MCP는 E2B 설치(4건·10분 예산, 남으면 다음 날 06:00) / `tool_updates.py`: 받아 본 MCP(30일)의 새 버전 카드 하루 1장, 도구 칸 맨 앞
- `run_daily.py`: 수집 → 정리 → 중복 제거 → 큐레이터(월요일은 관련 카드도) → 도구 목록·검증 요청 쌓기 → 발송 전 검증(`presend`) → 되돌림 1 → 해설가 → 되돌림 2 → 검증 노드 → 검증 칸 → 저장. 개발 모드는 is_test만, 트레이스 하나
  - `--users N`·`--limit N`(디버깅 `--users 1 --limit 40`). 모델 장애는 사용자·카드 단위로 건너뛰고 전원 실패면 종료 코드 2. 형식 실패 예시는 `tests/pipeline/format_failures.json`(git 추적 안 함)
- `briefing_mail.py`: 메일 본문(HTML·텍스트). 금요일은 `weekly.py`의 "이번 주 요약"(카드 데이터만, 모델 없음)을 맨 아래에. 카드·trace_id·피드백 서명 링크, 뉴스/도구/관련 칸, 빈 행, 검증 결과 줄과 고정 문구 두 개, `combine`(개발 모드 묶음: 목차 + 프로필별 구역, 구역마다 머리 안 되풀이). 색은 웹앱 디자인 토큰 값, 근거 링크는 원문과 다를 때만
- `deliver.py`: 미발송 briefings를 사용자별 메일로 Gmail SMTP 발송, 한 통마다 sent_at. 개발 모드는 받는 사람을 ADMIN_EMAILS로 바꾸고 프로필 전부를
  [개발 모드] 한 통으로 묶는다(실패하면 전부 미발송, 다음 시도에 다시 묶음). ADMIN_EMAILS 없으면 콘솔·DB만, 메일 설정 없으면 기록 안 함. `send_alert`: 실패 알림
- `scheduler.py`: 앱이 떠 있는 동안 06:00 검증(W1-a, 따로 도는 작업), 06:55 예열·DB 깨우기, 07:00 하루 실행, 알림 시각마다 발송 (KST). 놓친 실행은 22:00 전에 따라잡음. 실행 실패·빠진 사용자는 30분 뒤 그 사용자만 2번 더, 발송 실패는 10분 간격 2번 더, 끝내 실패하면 실패 알림 한 통, 월요일은 실행 전 기억 합치기(W4)
- `autorestart.py`: 할 일을 마칠 때마다 main 커밋이 바뀌었고 한가하면(06~09시 아님·실행 없음·다음 예정 10분 넘게) 스스로 꺼져 런처가 새 코드로 다시 띄움
- `watchdog.py`: 앱 바깥 감시. 작업 `toolscout watchdog`(10분마다, ps1이 먼저 꺼진 런처·멈춘 앱을 되살림)이 앱 응답과 알림 시각 30분 지난 사용자의 발송 여부를 보고 문제면 실패 알림(같은 날 같은 문제 한 번)

## 들어오고 나가는 데이터
- 들어옴: `sources/` 항목, 루트 `memory.py` 기억, `agent/` 카드
- 나감: Supabase items·briefings·seen, 실행 보고(건수·토큰·시간·trace_id), 아침 메일

## 관련
- `agent/`: 큐레이터·해설가 / 루트 `main.py`: 예약 시작, `mcp_server.py`: 해설가 원문 재조회(앱 8000 포트) / `routes/w1.py`: 수동 실행·발송·상태 / 검수 `tests/pipeline/`, `tests/verify/check_rollback.py`

## 할 일
- [ ] W4 나머지: 마감 리마인드 (미완료 검증 재시도는 06:00 W1-a가 맡음)
- [ ] 첫 월요일(9/21) 실제 관련 카드 확인. 9/15 기준 주제 판정된 도구 8건이라 매일 쌓인 뒤 본다
