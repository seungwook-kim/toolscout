# sources/

소스별 수집 파서. 상태: 10곳 구현, 벤처비트 제외 (계획안 9.1).

## 파일
- `common.py`: 정규화 항목 모양, 정직한 User-Agent HTTP 클라이언트, 날짜 해석, SourceResult(stats 포함)
- `rss.py`: RSS 6곳 (오픈AI, 구글 AI, AI타임스, 긱뉴스, 테크크런치 AI, 레딧). 긱뉴스는 항목 안 외부 링크를 source_url로, 없으면 skip_fetch(요약만)
- `hackernews.py`: Algolia, AI 또는 LLM (optionalWords), points 20 이상
- `mcp_registry.py`: 7일 창, GitHub 저장소 있는 서버, 게시자당 3건, 버전 업 별 50 이상, 별 수 상위 신규 20·버전 업 10, 항목에 install(packages·remotes)
- `github_stars.py`: 별 수 조회와 items.stars·stars_checked_at 24시간 캐시 (DB 없으면 메모리만)
- `skillsmp.py`: SkillsMP 스킬. 검색만 열려 있어 주제어 8개로 훑고, 갱신 시각을 못 믿어 창 대신 items에 없는 주소만 신규로 본다
  (게시자당 3건·별 수 상위 20건, 키 없으면 건너뜀)
- `anthropic_skills.py`: anthropics/skills 커밋, 바뀐 skills/<이름>/SKILL.md 폴더를 skill_url로 (검증관 read_skill용)
- `collect.py`: 전체 수집(뉴스 48시간·도구 7일 창. 뉴스가 48시간인 이유는 CHANGELOG 2026-09-21). 실패 소스는 기록하고 계속. MCP 레지스트리는 제한 시간 60초·2번 더 시도, 그래도 실패면 마지막 성공 결과(`%LOCALAPPDATA%\toolscout`)를 "수집 실패, 전날 기준"으로 재사용

## 들어오고 나가는 데이터
- 들어옴: RSS, Algolia API, MCP 레지스트리 API(목록·버전 이력), GitHub API(커밋·별 수)
- 나감: `SourceResult(source, items, fetched, error, stats)`, items는 `{title, url, published_at, summary, source, type}`

## 관련
- `pipeline/`: 출력을 받아 정리·중복 제거 / `tests/sources/`: 오늘 건수 리포트

## 할 일
- [ ] MCP 수집 115초 중 대부분이 레지스트리 목록·버전 이력 조회. 버전 이력도 캐시할지


- [ ] Glama 2차 테스트 (계획안 9.1 측정예정). SkillsMP는 2026-09-23에 붙였다
- [ ] SkillsMP 주제어 8개가 스킬 목록을 얼마나 덮는지. 2026-09-23 실측은 서로 다른 319건이었다
