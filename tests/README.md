# tests/

기능별 검수 기준 확인 스크립트. 상태: 만들 예정.

실행은 프로젝트 루트에서 `uv run python -m tests.<폴더>.<파일>` 형식으로 한다.

## 폴더
- `env/check_env.py`: pip check, langgraph·langchain 미설치, 필수 import 검사 → `env/check_env.json`
- `env/check_env_example.py`: `.env.example` 키 19개, `.env` git 무시 검사
- `mcp/`: MCP 서버 도구 목록·키 검문 (예정)
- `sources/`: 소스 수집 리포트 (예정)
- `docs/check_folder_docs.py`: 주요 폴더 README 30줄·CHANGELOG 형식·긴 줄표 검사
- `docs/check_readme.py`: 루트 README 사양(절, 배지, mermaid, 이모지 규칙) 검사

## 들어오는 데이터
- 각 폴더의 코드, 실제 외부 소스 응답

## 나가는 데이터
- 검수 결과 JSON·리포트 (통과/미통과)

## 관련
- 모든 주요 폴더 (기능 하나 끝날 때마다 여기에 검수 스크립트를 남긴다)
