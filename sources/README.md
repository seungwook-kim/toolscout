# sources/

소스별 수집 파서. 상태: [확인됨] 10곳 구현 (계획안 9.1).

## 파일
- `common.py`: 정규화 항목 모양, 정직한 User-Agent HTTP 클라이언트, 날짜 해석
- `rss.py`: RSS 7곳 (오픈AI, 구글 AI, AI타임스, 긱뉴스, 테크크런치 AI, 벤처비트, 레딧)
- `hackernews.py`: Algolia, AI 또는 LLM (optionalWords)
- `mcp_registry.py`: 공식 레지스트리, 7일 창 최신 버전
- `anthropic_skills.py`: anthropics/skills 커밋
- `collect.py`: 전체 수집. 뉴스 24시간·도구 7일 창, 실패 소스는 기록하고 계속

## 들어오고 나가는 데이터
- 들어옴: RSS, Algolia API, MCP 레지스트리 API, GitHub API
- 나감: `SourceResult(source, items, fetched, error)`, items는 `{title, url, published_at, summary, source, type}`

## 관련
- `pipeline/`: 출력을 받아 정리·중복 제거 / `tests/sources/`: 오늘 건수 리포트

## 할 일
- [ ] 수집량 기준 결정: MCP 레지스트리 7일 2,000건 이상, 해커뉴스 하루 189건
- [ ] 벤처비트 429 (정직한 UA 차단) 대응 결정
- [ ] GitHub PAT 넣고 anthropics/skills 재확인
- [ ] Glama, SkillsMP 2차 테스트 (계획안 9.1 측정예정)
