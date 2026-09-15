# routes/

웹앱 화면과 기능 API 라우터. 상태: 아침 브리핑 수동 실행 API 구현, 화면·피드백·질문은 예정 (계획안 9.3).

## 파일
- `w1.py`: 아침 브리핑 작업을 직접 부르는 API (X-Service-Key 검문). 평소에는 `pipeline/scheduler.py`가 07:00·08:00에 돈다
  `POST /api/w1/run?users=&limit=` 하루 실행(202, 중복이면 409), `POST /api/w1/send?date=` 지금 발송, `GET /api/w1/status`
- 웹앱 화면(`/`), 브리핑·피드백·질문 API(`/api/`), 관리자 트레이스 링크 (예정)

## 들어오고 나가는 데이터
- 들어옴: 관리자 HTTP 요청(서비스 키), 브라우저 요청, 이메일 링크 버튼(서명 토큰, 예정)
- 나감: 실행·발송 요약, 예약 상태(다음 예정·마지막 실행·발송), 카드 화면·피드백 기록·질문 답변(예정)

## 관련
- 루트 `main.py`: 이 라우터를 FastAPI 앱에 붙인다 / `pipeline/`: scheduler·run_daily·deliver
- `web/`: 정적 파일 / `tests/pipeline/check_deliver.py`: API 키 검문·상태

## 할 일
- [ ] 브리핑 조회 API (뼈대)
- [ ] 피드백 API와 링크 서명 토큰 검증 (부록 C)
- [ ] 질문 API와 게이트 연결 (부록 E)
- [ ] 관리자 카드 → Langfuse 트레이스 링크
