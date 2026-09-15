# n8n/

n8n 워크플로우 export 보관. 상태: W1 작성, 나머지 예정 (계획안 9.2).

## 파일
- `workflows/W1_daily.json`: 07:00 `POST /api/w1/run`(하루 실행 시작) / 08:00 `GET /api/w1/outbox` → 개발 모드면 보내지 않고
  `POST /api/w1/sent`만, 운영이면 사용자별 Send Email(SMTP) → 성공한 사용자만 `POST /api/w1/sent`. 시간대 Asia/Seoul, 가져오면 꺼진 상태

## 들어오고 나가는 데이터
- 들어옴: 앱 API 응답(발송함: 보내는 사람·받는 사람·제목·HTML·텍스트)
- 나감: 앱 API(`http://app:8000/api/w1/*`) 호출, 메일 발송

## 자격 증명 (n8n 화면에서 만든다. 값은 파일에 넣지 않는다)
- `toolscout 서비스 키`: Header Auth, 이름 `X-Service-Key`, 값은 앱의 MCP_SERVICE_KEY
- `toolscout Gmail SMTP`: SMTP, smtp.gmail.com 465 SSL, 사용자 GMAIL_USER, 비밀번호 GMAIL_APP_PASSWORD

## 관련
- 루트 `docker-compose.yml`: n8n 컨테이너(2.38.7, Node 24 필요) / `routes/w1.py`: 부르는 API / `tests/n8n/check_workflows.py`
- `.github/workflows/ci.yml`: n8n 컨테이너에 워크플로우를 실제로 가져와 노드 수 확인

## 할 일
- [ ] n8n 화면에서 자격 증명 2개 만들고 W1 켜기, 실제 07:00·08:00 실행 확인 (로컬은 Docker·Node 24 없음)
- [ ] 08:00에 하루 실행이 안 끝났으면 기다릴지(`GET /api/w1/status`) 결정, 실패 알림은 W4
- [ ] W2 질문, W3 피드백 (상호작용 단계) / W0 카카오 토큰 갱신, W4 주간 합치기·야간 재실행 (뼈대 완성 후)
