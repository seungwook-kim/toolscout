# 소스 수집 리포트

측정: 2026-09-14 06:45 UTC · `uv run python -m tests.sources.run_today`로 다시 만든다.
뉴스 24시간, 도구 7일 창. 목표 300건 안팎(±20%).

## 필터: MCP 게시자당 3건, 해커뉴스 20점 이상

| 소스 | 방식 | 처리 규칙 | 받은 건수 | 남긴 건수 | 상태 |
|---|---|---|---|---|---|
| openai | RSS https://openai.com/news/rss.xml | 날짜 창 필터 (전체 글이 옴) | 1192 | 1 | OK |
| google_ai | RSS https://blog.google/technology/ai/rss/ |  | 20 | 0 | OK |
| aitimes | RSS https://www.aitimes.com/rss/allArticle.xml | 시간대 없는 날짜는 KST | 50 | 14 | OK |
| geeknews | RSS https://news.hada.io/rss/news |  | 50 | 50 | OK |
| techcrunch_ai | RSS https://techcrunch.com/category/artificial-intelligence/feed/ |  | 19 | 2 | OK |
| reddit_localllama | RSS https://www.reddit.com/r/LocalLLaMA/.rss | User-Agent 필수 | 25 | 22 | OK |
| hackernews | Algolia API, AI 또는 LLM (optionalWords) | OR는 optionalWords로, points N 이상 | 18 | 18 | OK |
| mcp_registry | 공식 레지스트리 API /v0/servers, updated_since | 7일 창, GitHub 저장소, 게시자당 N건, 버전 업은 별 50 이상 | 5289 | 835 | OK |
| anthropic_skills | GitHub API anthropics/skills 커밋 | 7일 창, PAT 있으면 사용 | 1 | 1 | OK |

MCP 레지스트리 단계별: 창_안_active 5289, github_저장소 4437, 게시자 1709, 신규 670, 버전업_별50이상 165, 버전업_제외 1197, 게시자_상한으로_제외 2405

합계: 943건 · 소요 136.9초

## 필터: MCP 게시자당 2건, 해커뉴스 30점 이상

| 소스 | 방식 | 처리 규칙 | 받은 건수 | 남긴 건수 | 상태 |
|---|---|---|---|---|---|
| openai | RSS https://openai.com/news/rss.xml | 날짜 창 필터 (전체 글이 옴) | 1192 | 1 | OK |
| google_ai | RSS https://blog.google/technology/ai/rss/ |  | 20 | 0 | OK |
| aitimes | RSS https://www.aitimes.com/rss/allArticle.xml | 시간대 없는 날짜는 KST | 50 | 14 | OK |
| geeknews | RSS https://news.hada.io/rss/news |  | 50 | 50 | OK |
| techcrunch_ai | RSS https://techcrunch.com/category/artificial-intelligence/feed/ |  | 19 | 2 | OK |
| reddit_localllama | RSS https://www.reddit.com/r/LocalLLaMA/.rss | User-Agent 필수 | 25 | 22 | OK |
| hackernews | Algolia API, AI 또는 LLM (optionalWords) | OR는 optionalWords로, points N 이상 | 11 | 11 | OK |
| mcp_registry | 공식 레지스트리 API /v0/servers, updated_since | 7일 창, GitHub 저장소, 게시자당 N건, 버전 업은 별 50 이상 | 5289 | 811 | OK |
| anthropic_skills | GitHub API anthropics/skills 커밋 | 7일 창, PAT 있으면 사용 | 1 | 1 | OK |

MCP 레지스트리 단계별: 창_안_active 5289, github_저장소 4437, 게시자 1709, 신규 648, 버전업_별50이상 163, 버전업_제외 1154, 게시자_상한으로_제외 2472

합계: 912건 · 소요 3.3초

판정: 목표 초과, 결정 필요

## 제외한 소스

| 소스 | 방식 | 사유 |
|---|---|---|
| venturebeat_ai | RSS https://venturebeat.com/category/ai/feed/ | HTTP 429, 봇 UA 차단, 우회 안 함, 제외 |
