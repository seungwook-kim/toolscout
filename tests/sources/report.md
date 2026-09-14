# 소스 수집 리포트

측정: 2026-09-13 13:45 UTC · `uv run python -m tests.sources.run_today`로 다시 만든다.
원래 09-11 리포트는 저장소에 없어서 이 파일은 새로 측정해 작성했다. 뉴스 24시간, 도구 7일 창 기준.

| 소스 | 방식 | 처리 규칙 | 받은 건수 | 창 안 건수 | 상태 |
|---|---|---|---|---|---|
| openai | RSS https://openai.com/news/rss.xml | 날짜 창 필터 (전체 글이 옴) | 1192 | 1 | OK |
| google_ai | RSS https://blog.google/technology/ai/rss/ |  | 20 | 0 | OK |
| aitimes | RSS https://www.aitimes.com/rss/allArticle.xml | 시간대 없는 날짜는 KST | 50 | 18 | OK |
| geeknews | RSS https://news.hada.io/rss/news |  | 50 | 38 | OK |
| techcrunch_ai | RSS https://techcrunch.com/category/artificial-intelligence/feed/ |  | 19 | 2 | OK |
| venturebeat_ai | RSS https://venturebeat.com/category/ai/feed/ | 요약 500자 절단 | 0 | 0 | 실패 (HTTP 429) |
| reddit_localllama | RSS https://www.reddit.com/r/LocalLLaMA/.rss | User-Agent 필수 | 25 | 20 | OK |
| hackernews | Algolia API, AI 또는 LLM (optionalWords) | OR는 optionalWords로 | 189 | 189 | OK |
| mcp_registry | 공식 레지스트리 API /v0/servers, updated_since | 7일 창, 최신 버전만 | 2000 | 1964 | 실패 (페이지 상한 20회 도달, 일부만 수집) |
| anthropic_skills | GitHub API anthropics/skills 커밋 | 7일 창, PAT 있으면 사용 | 1 | 1 | OK |

창 안 합계: 2233건
