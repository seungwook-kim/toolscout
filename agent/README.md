# agent/

에이전트 3개와 공통 판단 루프. 상태: 구현, 되돌림 2개 포함 (계획안 5장, 9.3, 부록 D).

## 파일
- `loop.py`: `run(role, system_prompt, user_input, allowed_tools, max_steps, max_tool_calls, tool_guard)`. 모델 → 도구 요청 → MCP 실행 → 재호출(MCP 읽기 240초) / `injection.py`: 프롬프트 인젝션 방어. 바깥 글 정리(보이지 않는 글자·<data> 흉내·채팅 틀 토큰), 지시 문장 찾기(경고만), 카드 글 링크·흔적 검사, 설치 명령은 그 도구 자신의 주소만
- `skill_check.py`: read_skill 구현. GitHub·SkillsMP 원문 10,000자·<data>, 정규식 5종(외부 전송·자격증명·권한 상승·숨은 명령·판독 지시)과 인용
- `probe.py`: probe_mcp 구현. E2B에서 ① 설치 90초(네트워크) ② 실행 30초(도움말만 나오면 MCP 하위 명령으로 1회 더, 없으면 미확인) ③ 도구 목록(차단, mcp/sandbox_probe.py) ④ 인증 요구, npm은 Node 22 준비, 가드·하루 30건, probes 저장
- `tracing.py`: Langfuse 스팬 래퍼(키 없으면 로컬 JSONL, trace_id 항상, `trace_url()`) / `structured.py`: JSON 규격 응답(온도 0, 규격을 Anthropic 구조화 출력 스키마로 전달, 검사, 1회 재시도, 실패 예시·모델 장애 기록)
- `same_story.py`: 같은 소식 묶기·겹침 빼기(운영 gpt-4o-mini, 개발 구독 Sonnet) / `owners.py`: 도구 후보 게시자 반복 줄이기(최근 7일 본 게시자 빼기·하루 한 건) / `card_why.py`: 카드 이유를 관심 주제·쓰는 도구 근거로 / `headline.py`: 오늘의 큰 소식 1~2칸(중요도·다룬 곳·공식, 새 기사가 하나라도 있어야) / `importance.py`: 뉴스 중요도를 Jev 점수로(개발 모드는 Jev가 못 매긴 기사만 구독 Haiku 20건 묶음, 그것도 실패하면 선별 점수) / `curator.py`: 큐레이터. 20건 무작위 묶음 선별 → 사용자별 뉴스 10·도구 3(본 항목·가중치 -5 제외, 뉴스는 고른 뒤 별점 순, 도구는 가중치 순) → 검증 요청 5. `select_memo.py`: 오늘·어제 판정한 뉴스는 다시 판정하지 않고 그 판정을 쓴다(select_memos 표, 7일 보관). 뉴스는 AI 관련이면 후보, 사용자 뉴스는 원문 26시간 안·별점 3 이상, 별점 > 가중치 순으로 큰 소식 포함 최대 10건
  월요일은 관련 카드(F3-b): 도구 목록 30건에서 최대 3개, 이름 일치 > 가중치 (`pick_related`). `replan_failed`: 되돌림 1 대체·비움 판단
- `explainer.py`: 해설가. 항목마다 fetch_article 1회 + 모델 1회로 초안 카드. 관련도 3 미만·프로필과 안 이어지면 반려, 못 읽으면 "원문 확인 필요"(피드 글 본문 source_text는 읽은 것으로). 장단점 근거 링크는 카드 링크로 맞추고 다른 사이트 근거는 뺌
  `answer()`: 질문 답(후보·맥락 입력, fetch_article 3회, 600자, 후보 링크만 출처, 형식 틀리면 1회 재시도)
- `term_dict.json`: 영어 이름 → 한글 표기 사전. 질문창 `routes/ask.py` 키워드 확장용(Claude가 만든 초안, 사람 검토 전)
- `glossary.md`: 해설가 용어집 30개와 표기 원칙. 프롬프트에 그대로 붙는다
- `schemas.py`: 주제 10개(확정)와 주제별 경계(TOPIC_GUIDE, 선별 프롬프트에 붙음), 선별·후보·검증 요청·해설가 출력·카드·질문 답 규격(pydantic). 검증 노드도 같은 규격을 쓴다
- `verifier.py`: 검증관. MCP는 레지스트리 설치 정보로 바로(`registry_plan`), 없을 때만 모델이 README로 판단 → probe_mcp, 스킬은 read_skill → 판독과 정규식 비교
  (다르면 확인 필요, 공식은 생략). 항목당 도구 4회, 요청 상태 기록, `reverify`는 되돌림 2용

## 들어오고 나가는 데이터
- 들어옴: `pipeline/`의 정리된 항목, 루트 `memory.py`의 사용자 기억, MCP 도구 결과(`<data>` 원문)
- 나감: 큐레이터 `{selected, plans, verify, stats}`, 해설가 `{users: [{cards, rejected, format_failed}], stats}`, 루프 이벤트

## 관련
- 루트 `models.py`·`providers.py`: 역할별 모델 호출 / 루트 `mcp_server.py`: 루프가 부르는 도구

## 할 일
- [ ] 해설가 실제 모델 검수(같은 항목 for_me 3쌍·반려 이유). 로컬 모델로 한도 걱정 없이 돌릴 수 있다
- [ ] 선별 기준 편차: Gemini 34건, 대체 모델 94건. 로컬 모델 결과와 같은 데이터로 비교
- [ ] Langfuse 스팬 전송 제한 시간(5초) 초과로 최상위 스팬이 빠진 트레이스 1건. 제한 시간 조정 여부 결정
- [ ] 운영 전환 때 검증관 판독(Opus 5)을 개발 모드(구독 Sonnet 5) 결과와 같은 스킬로 비교
