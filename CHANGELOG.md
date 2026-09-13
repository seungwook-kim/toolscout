# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`, 남은 작업은 각 폴더 README의 `## 할 일`에 있다.

- 세션 1 · 2026-09-13 · 0단계·1단계 앞부분 (진행 중)
  - 끝난 것 (main 머지): 1 폴더 구조·문서, 2 루트 README, 3 pyproject·환경 검사, 4 .env.example, 6 models.py·agent/tracing.py, 7 db.py(Supabase 전용), 폴더 README 할 일 절, .gitignore 정리
  - 미완: 5 docker는 `feat/05-docker` 브랜치 (docker 미설치로 compose config 미통과, 머지 보류). 8 sources ~ 12 main.py 진행 예정
  - 결정됨: DB는 Supabase 하나(SQLite 안 씀). 로컬 작업 도구 파일은 저장소에서 제외
  - 결정 필요: Docker 설치, .env 키·Supabase 연결 문자열, Postgres 드라이버, 로컬 .env 로딩 방법(python-dotenv), Anthropic 과부하 529 전환 포함 여부, 계획안 부록 A 트리 부재, mcp/ 폴더 용도, tests/sources/report.md 원본 없음
  - 다음 시작점: 착수 8번 sources
