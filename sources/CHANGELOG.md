# sources/ CHANGELOG

- 2026-09-21 · collect.NEWS_WINDOW 24시간 → 48시간 · 하루 1회 07:00 실행이라 24시간이면 기사가 후보에 오를 기회가 한 번뿐이고, 밀리면 창 밖으로 나가 다시 못 온다. 9월 17일 17시 36분 Jev 공개 기사가 9월 18일 실행에서 밀린 뒤 19일·20일 브리핑에 한 번도 오르지 못한 것을 실측 · check_news_window 10항목·check_fallbacks 7항목 통과

- 2026-09-15 · mcp_registry 항목에 install(레지스트리 packages·remotes 요약), anthropic_skills 항목에 skill_url(커밋이 바꾼 SKILL.md 폴더) · 세션 8 검증관이 설치 명령·원문 주소를 정하게 · check_fallbacks 통과
- 2026-09-15 · collect: MCP 레지스트리 제한 시간 60초·실패 시 2번 더 시도·마지막 성공 결과 저장과 재사용("수집 실패, 전날 기준"), rss: 긱뉴스 항목 안 외부 링크를 source_url로·없으면 skip_fetch, common.http_client 제한 시간 인자 · 세션 7 결정 4·5, 레지스트리 ReadTimeout 2회·HTTP 500 1회 실측, 긱뉴스 RSS에는 외부 링크가 없음 확인 · check_fallbacks 7항목 통과

- 2026-09-14 · README 할 일 갱신(레지스트리 ReadTimeout 관찰 추가, 저장소 공유 MCP는 persist가 앞 순위만 저장해 해결) · 첫 실제 하루 실행 결과 반영 · 코드 변경 없음

- 2026-09-14 · MCP 별 수 상위 신규 20·버전 업 10, github_stars.py(items에 별 수 24시간 캐시) 추가 · 수집량 결정(MCP 상위 30건, 첫날만 전량 조회) · run_today 통과, 161건(중복 제거 후 161, 선별 호출 9회), 2회차 별 수 캐시 1,821건·새 조회 17건
- 2026-09-14 · MCP 레지스트리 필터(GitHub 저장소, 게시자당 3건, 버전 업 별 50 이상)와 해커뉴스 points 20 추가, 벤처비트 제외, config 로더 연결 · 수집량 과다·429 차단에 대한 사용자 결정 · run_today 통과, 943건(3건·20점) → 912건(2건·30점), 목표 300건 초과로 결정 필요
- 2026-09-13 · [확인됨] 소스 10곳 파서와 collect 추가 · 착수 8번 · run_today 구조 검사 통과, 창 안 2,233건, 벤처비트 429 실패, MCP 레지스트리 페이지 상한 도달
- 2026-09-13 · README에 할 일 절 추가 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
