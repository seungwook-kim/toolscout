# CHANGELOG (세션 단위)

새 세션은 맨 위 항목을 읽고 시작한다. 폴더별 상세 이력은 각 폴더의 `CHANGELOG.md`에 있다.

- 세션 1 · 2026-09-13 · 0단계·1단계 앞부분 (사용자 토큰 소진으로 7번 앞에서 중단)
  - 끝난 것 (main 머지): 1 폴더 구조·문서, 2 루트 README, 3 pyproject·환경 검사, 4 .env.example, 6 models.py·agent/tracing.py
  - 미완: 5 docker는 `feat/05-docker` 브랜치에 커밋만 함 (docker 미설치로 compose config 미통과, 머지 보류). 7 db.py ~ 12 main.py 시작 전
  - 결정 필요: Docker 설치, .env 키 입력, 로컬 .env 로딩 방법(python-dotenv 추가 여부), Anthropic 과부하 529를 대체 전환에 넣을지, 계획안 부록 A에 폴더 트리 없음, mcp/ 폴더 용도, tests/sources/report.md 원본 없음, GitHub push 여부(아직 안 함)
  - 다음 시작점: 착수 프롬프트 7번 db.py부터 12번까지. 5번은 Docker 설치 후 `uv run python -m tests.env.check_docker` 재실행해 통과하면 머지
