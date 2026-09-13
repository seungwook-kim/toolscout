# sources/

소스별 수집 파서. 상태: 예정 (계획안 9.1).

## 파일
- 계획안 9.1에서 [확인됨] 표시된 소스의 파서 (예정)

## 들어오고 나가는 데이터
- 들어옴: RSS, 해커뉴스 Algolia API, MCP 공식 레지스트리 API, GitHub API
- 나감: `{title, url, published_at, summary, source, type}` 목록. type은 news, mcp, skill

## 관련
- `pipeline/`: 이 폴더의 출력을 받아 정리하고 중복을 제거한다
- `n8n/`: W1이 07:00에 수집을 부른다 (예정)

## 할 일
- [ ] [확인됨] 소스 10곳 파서, 오늘 소스별 건수 보고 (착수 8번)
- [ ] `tests/sources/report.md` 새로 작성 (원본 없음)
- [ ] GitHub PAT 넣고 anthropics/skills 커밋 수집 확인
- [ ] Glama, SkillsMP 2차 테스트 (계획안 9.1 측정예정)
