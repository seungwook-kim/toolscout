# sources/

소스별 수집 파서. 상태: 만들 예정 (계획안 9.1).

## 파일
- 계획안 9.1에서 [확인됨] 표시된 소스의 파서 (예정)

## 들어오는 데이터
- 외부 RSS, 해커뉴스 Algolia API, MCP 공식 레지스트리 API, GitHub API

## 나가는 데이터
- 정규화 항목 목록 `{title, url, published_at, summary, source, type}`
- `type`은 `news`, `mcp`, `skill` 중 하나

## 관련
- `pipeline/`: 이 폴더의 출력을 받아 정리하고 중복을 제거한다
- `n8n/`: W1이 07:00에 수집을 부른다 (예정)
