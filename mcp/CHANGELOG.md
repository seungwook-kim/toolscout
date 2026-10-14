# mcp/ CHANGELOG

- 2026-10-14 · 루트 mcp_server.wrap_data가 agent/injection.clean으로 감쌀 글을 정리(전에는 정확한 </data>만 바꿈, 대소문자·띄어쓰기 변형과 보이지 않는 글자는 통과) · 인젝션 방어 · check_injection·list_tools 통과
- 2026-10-14 · 루트 mcp_server.ALLOWED_DOMAINS에 huggingface.co·arxiv.org · 레딧 링크 글이 가리키는 모델 카드·논문을 fetch_article로 읽게(sources/rss.reddit_post) · 실측 Hugging Face 모델 카드 2건·arXiv 초록 1건 ok(본문 3,000자)
- 2026-09-15 · sandbox_probe.py 추가(stdio·http 두 방식 initialize·tools/list) · 세션 8 검증관 1단계, 부록 D ③ · E2B에서 server-everything 도구 13개(네트워크 차단 상태)·DeepWiki 원격 3개·Apify 원격 401 확인
- 2026-09-14 · 폴더 용도 확정: 공개 MCP 연결 설정 예시(client-config.example.json)와 E2B 안 tools/list 클라이언트 스크립트 자리 · 사용자 승인 · check_folder_docs 통과
- 2026-09-13 · README 관련·할 일에 루트 mcp_server.py 구현 상태 반영 · 착수 11번 서버 골격 완료 · list_tools 통과(7항목)
- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
