# routes/

웹앱 화면과 기능 API 라우터. 상태: n8n W1용 API 구현, 화면·피드백·질문은 예정 (계획안 9.3).

## 파일
- `w1.py`: n8n W1 API (X-Service-Key 검문). `POST /api/w1/run` 하루 실행 시작(202, 중복이면 409), `GET /api/w1/status`,
  `GET /api/w1/outbox?date=` 미발송 사용자별 메일, `POST /api/w1/sent` sent_at 기록
- 웹앱 화면(`/`), 브리핑·피드백·질문 API(`/api/`), 관리자 트레이스 링크 (예정)

## 들어오고 나가는 데이터
- 들어옴: n8n HTTP 요청(서비스 키), 브라우저 요청, 이메일 링크 버튼(서명 토큰, 예정)
- 나감: 하루 실행 상태, 발송함(제목·HTML·텍스트·trace_id), 카드 화면·피드백 기록·질문 답변(예정)

## 관련
- 루트 `main.py`: 이 라우터를 FastAPI 앱에 붙인다 / `pipeline/`: run_daily·deliver / `n8n/workflows/`: W1
- `web/`: 정적 파일 / `tests/pipeline/check_deliver.py`: API 키 검문·발송함·발송 기록

## 할 일
- [ ] 브리핑 조회 API (뼈대)
- [ ] 피드백 API와 링크 서명 토큰 검증 (부록 C)
- [ ] 질문 API와 게이트 연결 (부록 E)
- [ ] 관리자 카드 → Langfuse 트레이스 링크
