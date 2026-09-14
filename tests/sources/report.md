# 소스 수집 리포트

측정: 2026-09-14 09:53 UTC · `uv run python -m tests.sources.run_today`로 다시 만든다.
뉴스 24시간, 도구 7일 창. 목표 300건 안팎(±20%).

## 필터: MCP 게시자당 3건, 해커뉴스 20점 이상

| 소스 | 방식 | 처리 규칙 | 받은 건수 | 남긴 건수 | 상태 |
|---|---|---|---|---|---|
| openai | RSS https://openai.com/news/rss.xml | 날짜 창 필터 (전체 글이 옴) | 1193 | 1 | OK |
| google_ai | RSS https://blog.google/technology/ai/rss/ |  | 20 | 0 | OK |
| aitimes | RSS https://www.aitimes.com/rss/allArticle.xml | 시간대 없는 날짜는 KST | 50 | 38 | OK |
| geeknews | RSS https://news.hada.io/rss/news |  | 50 | 50 | OK |
| techcrunch_ai | RSS https://techcrunch.com/category/artificial-intelligence/feed/ |  | 19 | 2 | OK |
| reddit_localllama | RSS https://www.reddit.com/r/LocalLLaMA/.rss | User-Agent 필수 | 25 | 22 | OK |
| hackernews | Algolia API, AI 또는 LLM (optionalWords) | OR는 optionalWords로, points N 이상 | 17 | 17 | OK |
| mcp_registry | 공식 레지스트리 API /v0/servers, updated_since | 7일 창, GitHub 저장소, 게시자당 N건, 버전 업 별 50 이상, 별 수 상위 신규 20·버전 업 10 | 5257 | 30 | OK |
| anthropic_skills | GitHub API anthropics/skills 커밋 | 7일 창, PAT 있으면 사용 | 1 | 1 | OK |

MCP 레지스트리 단계별: 창_안_active 5257, github_저장소 4383, 게시자 1704, 신규 582, 버전업_별50이상 169, 버전업_제외 1324, 게시자_상한으로_제외 2308, 신규_상위 20, 버전업_상위 10, 별수_DB캐시 1821, 별수_새조회 17, 별수_DB저장 17

합계: 161건 · 중복 제거 후 161건 · 큐레이터 선별 호출 9회 · 소요 114.6초

판정: 목표 안팎, 확정

## 제외한 소스

| 소스 | 방식 | 사유 |
|---|---|---|
| venturebeat_ai | RSS https://venturebeat.com/category/ai/feed/ | HTTP 429, 봇 UA 차단, 우회 안 함, 제외 |
