# mcp/

MCP 부속 파일 자리. 상태: E2B 샌드박스 안 클라이언트 구현, 공개 MCP 설정 예시는 아직.

서버 코드는 이 폴더가 아니라 루트 `mcp_server.py`에 있다.

## 파일
- `sandbox_probe.py`: E2B 샌드박스에 올려 실행하는 MCP 클라이언트(표준 라이브러리만). stdio 서버를 띄워 initialize·tools/list, 또는 원격 URL GET·streamable HTTP로 같은 요청. 결과 JSON 한 줄(도구 목록·에러·stderr 끝 2,000자)
- `client-config.example.json` (예정): 공개 MCP 연결 설정 예시

## 주의
- 이 폴더에 `__init__.py`를 두지 않는다. 두면 설치된 `mcp` SDK 패키지를 가린다.

## 들어오고 나가는 데이터
- 들어옴: 공개 도구 3종 규격(설정 예시), 검증 대상 MCP의 설치 명령(E2B 스크립트)
- 나감: 사용자가 복사할 설정 JSON, 샌드박스 안 도구 목록 결과

## 관련
- 루트 `mcp_server.py`: 내부 도구 6종 골격, `X-Service-Key` 검문
- `agent/probe.py`: 샌드박스를 만들고 이 스크립트를 올려 4단계 중 ③에 쓴다 / `agent/verifier.py`: 검증관

## 할 일
- [ ] `client-config.example.json` (공개 도구 3종 구현 후)
- [ ] lookup_registry, check_pricing 구현
