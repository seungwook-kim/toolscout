# tests/ CHANGELOG

- 2026-09-14 · sources/run_today.py 필터 재측정 방식으로 변경, check_models·check_tables·run_loop에 DEV_MODE·Supabase·실제 모델 조건 추가 · 수집 필터·개발 모델표 승인 반영 · run_today 통과(943→912건, 목표 초과), 나머지는 키 문제로 실제 호출 부분 미통과
- 2026-09-14 · check_docker.py를 GitHub Actions CI 결과로 판정하도록 변경 · 로컬 docker 없이 5번 검수 · 통과(CI 4단계 success, 정적 8항목)
- 2026-09-14 · env/check_config.py 추가 · .env 값 출력 금지 규칙과 config 로더 · 통과(5항목)
- 2026-09-13 · agent/run_loop.py 추가 · 착수 10번 루프 동작 · 통과(8항목), 실제 모델 실행은 ANTHROPIC_API_KEY 없어 미실행
- 2026-09-13 · app/check_main.py 추가 · 착수 12번 uvicorn 기동 · 통과(5항목), docker compose up app은 feat/05-docker 검수로 넘김
- 2026-09-13 · mcp/list_tools.py, list_tools_result.json 추가 · 착수 11번 도구 목록·키 검문 · 통과(7항목), 긱뉴스 HTML 403이라 GitHub 페이지로 가져오기 확인
- 2026-09-13 · pipeline/run_dedupe.py, dedupe_counts.json 추가 · 착수 9번 전후 건수 · 통과(7항목), 2,233 → 2,229 → 2,227
- 2026-09-13 · sources/run_today.py, today_counts.json, report.md 추가 · 착수 8번 소스별 건수 실측(원본 리포트 없어 새로 작성) · 구조 검사 4항목 통과
- 2026-09-13 · README에 할 일 절 추가, check_folder_docs가 할 일 절도 검사 · 폴더마다 남은 작업을 README 한 곳에서 보려고 · check_folder_docs 통과
- 2026-09-13 · db/check_tables.py 추가 · db.py 검수(Supabase 전용, SQLite 제외 결정 반영) · 통과(8항목), Supabase 실제 생성은 미설정으로 미실행
- 2026-09-13 · models/check_models.py 추가 · models.py 검수 · 통과(10항목), 실제 API 호출은 키 없어 미실행
- 2026-09-13 · env/check_env_example.py 추가 · .env.example 키 목록과 .env 무시 검수 · 통과(4항목)
- 2026-09-13 · env/check_env.py, check_env.json 추가 · 기술 고정 설치 후 langgraph 미설치 실측 · 통과(9항목, pip check는 uv pip으로 실행)
- 2026-09-13 · docs/check_readme.py 추가, 추적되던 __pycache__ 제거 · 루트 README 사양 검수 · 통과(15항목)
- 2026-09-13 · docs/check_folder_docs.py 추가 · 폴더 문서 규칙 검수 · 통과(9개 폴더)
- 2026-09-13 · 폴더 생성 · 계획안 v3.2 기준 · 검수 없음
