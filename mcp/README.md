# mcp/

MCP 부속 파일 자리. 상태: 용도 확정, 파일은 아직 없음.

서버 코드는 이 폴더가 아니라 루트 `mcp_server.py`에 있다.

## 파일 (예정)
- `client-config.example.json`: 공개 MCP 연결 설정 예시 (Claude Code·Claude Desktop용, 주소와 MCP 키 자리)
- E2B 샌드박스 안에서 설치한 MCP의 `initialize`·`tools/list`를 부르는 클라이언트 스크립트 (검증관 4단계 중 ③)

## 주의
- 이 폴더에 `__init__.py`를 두지 않는다. 두면 설치된 `mcp` SDK 패키지를 가린다.

## 들어오고 나가는 데이터
- 들어옴: 공개 도구 3종 규격(설정 예시), 검증 대상 MCP의 설치 명령(E2B 스크립트)
- 나감: 사용자가 복사할 설정 JSON, 샌드박스 안 도구 목록 결과

## 관련
- 루트 `mcp_server.py`: 내부 도구 6종 골격, `X-Service-Key` 검문
- `agent/verifier.py`: E2B 스크립트를 쓰는 검증관 (뼈대 완성 후)

## 할 일
- [ ] `client-config.example.json` (공개 도구 3종 구현 후)
- [ ] E2B 안 tools/list 클라이언트 스크립트 (검증관 단계)
- [ ] lookup_registry, check_pricing 구현 / probe_mcp, read_skill은 뼈대 완성 후
