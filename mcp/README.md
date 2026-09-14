# mcp/

MCP 관련 부속 파일 자리. 상태: 비어 있음.

서버 코드는 이 폴더가 아니라 루트 `mcp_server.py`에 있다.
계획안에 이 폴더의 파일 목록이 없어 용도는 확정 필요. 공개 MCP 연결 설정 예시를 둘 후보로 적어 둔다.

## 주의
- 이 폴더에 `__init__.py`를 두지 않는다. 두면 설치된 `mcp` SDK 패키지를 가린다.

## 들어오고 나가는 데이터
- 들어옴: 없음 / 나감: 없음 (예정)

## 관련
- 루트 `mcp_server.py`: 내부 도구 6종 골격, `X-Service-Key` 검문 (fetch_article·get_user_memory만 구현)
- `tests/mcp/list_tools.py`: 도구 목록·키 검문 검수

## 할 일
- [ ] 폴더 용도 확정
- [ ] lookup_registry, check_pricing 구현 / probe_mcp, read_skill은 뼈대 완성 후
- [ ] 공개 MCP 연결 설정 예시 작성 (공개 도구 3종 구현 후)
