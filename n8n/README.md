# n8n/

n8n 워크플로우 export 보관. 상태: 만들 예정 (계획안 9.2).

## 파일
- `workflows/`: W0~W4 워크플로우 JSON export (예정)
  - W0 카카오 토큰 갱신, W1 07:00 수집~08:00 발송, W2 질문, W3 피드백, W4 주간·야간 작업

## 들어오는 데이터
- n8n 편집기에서 export한 JSON

## 나가는 데이터
- 앱 API(`/api/`)와 MCP 서버(`/mcp`) 호출

## 관련
- 루트 `docker-compose.yml`: n8n 컨테이너
