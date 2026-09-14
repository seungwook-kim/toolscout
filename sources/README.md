# sources/

소스별 수집 파서. 상태: 9곳 구현, 벤처비트 제외 (계획안 9.1).

## 파일
- `common.py`: 정규화 항목 모양, 정직한 User-Agent HTTP 클라이언트, 날짜 해석, SourceResult(stats 포함)
- `rss.py`: RSS 6곳 (오픈AI, 구글 AI, AI타임스, 긱뉴스, 테크크런치 AI, 레딧)
- `hackernews.py`: Algolia, AI 또는 LLM (optionalWords), points 20 이상
- `mcp_registry.py`: 7일 창, GitHub 저장소 있는 서버, 게시자당 3건, 버전 업 별 50 이상, 별 수 상위 신규 20·버전 업 10
- `github_stars.py`: 별 수 조회와 items.stars·stars_checked_at 24시간 캐시 (DB 없으면 메모리만)
- `anthropic_skills.py`: anthropics/skills 커밋
- `collect.py`: 전체 수집. 필터 값·캐시를 받아 재측정 가능, 실패 소스는 기록하고 계속

## 들어오고 나가는 데이터
- 들어옴: RSS, Algolia API, MCP 레지스트리 API(목록·버전 이력), GitHub API(커밋·별 수)
- 나감: `SourceResult(source, items, fetched, error, stats)`, items는 `{title, url, published_at, summary, source, type}`

## 관련
- `pipeline/`: 출력을 받아 정리·중복 제거 / `tests/sources/`: 오늘 건수 리포트

## 할 일
- [ ] MCP 수집 115초 중 대부분이 레지스트리 목록·버전 이력 조회. 버전 이력도 캐시할지
- [ ] 2026-09-14 첫 실제 하루 실행에서 MCP 레지스트리가 ReadTimeout(20초)으로 통째로 빠져 도구 후보 0건. 재시도·제한 시간 결정
- [ ] Glama, SkillsMP 2차 테스트 (계획안 9.1 측정예정)
