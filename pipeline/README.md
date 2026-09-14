# pipeline/

수집 이후 하루 실행 순서. 상태: 발송 전까지 구현 (계획안 9.2 W1, 부록 B 1~6).

## 파일
- `normalize.py`: HTML·엔티티 제거, 공백 정리, URL 정규화(추적 파라미터·# 제거)
- `dedupe.py`: 링크 중복 제거(MCP는 이름 기준), 뉴스 제목 유사도 0.85 이상 묶기, 대표는 공식 > 매체 > 커뮤니티
- `validate.py`: 검증 노드. 카드 규격·글자 수·for_me 한 문장·근거 링크·한글 비율(어절 60%). 실패면 해설가 1회 재시도, 또 실패면 제외·트레이스에 이유
- `persist.py`: 통과 카드를 items(upsert)·briefings(trace_id, sent_at null)·seen에 저장. 카드 0건이면 empty_reason 행 하나. 발송한 사용자는 건너뛰고 미발송은 다시 씀
- `run_daily.py`: 수집 → 정리 → 중복 제거 → 큐레이터 → 해설가 → 검증 노드 → 저장. 개발 모드는 is_test 사용자만, 실행 전체가 트레이스 하나
  - `--users N`·`--limit N`(큐레이터 입력 상위 N, 뉴스·도구 비율 유지). 디버깅은 `--users 1 --limit 40`, 전량은 하루 1회
  - 모델 장애는 사용자·카드 단위로 건너뛰고, 대상 사용자가 모두 실패하면 종료 코드 2. 보고에 사용한 제공자·전환 사유
  - 개발 모드 형식 실패 예시는 `tests/pipeline/format_failures.json`에 쌓는다

## 들어오고 나가는 데이터
- 들어옴: `sources/` 항목 `{title, url, published_at, summary, source, type}`, 루트 `memory.py` 기억, `agent/` 카드
- 나감: 정리 항목(+ `also_reported_by`), Supabase items·briefings·seen, 실행 보고(건수·토큰·시간·trace_id)

## 관련
- `agent/`: 큐레이터·해설가 / 루트 `mcp_server.py`: 해설가 원문 재조회(앱 서버가 떠 있어야 함)
- `tests/pipeline/run_dedupe.py`: 전후 건수 / `tests/pipeline/run_daily.py`: 검증 노드·저장·멱등, 실제 한 번 실행

## 할 일
- [ ] 이메일 발송과 sent_at 기록 (다음 세션), n8n W1이 run_daily를 부르게 연결. empty_reason 행은 "오늘 볼 만한 게 없었음"으로 발송
- [ ] 전량 실행(사용자 2명·입력 전체) 하루 1회. 첫 실행(사용자 1·입력 40)은 486초. 구간별 시간은 아직 안 나눠 봤다
- [ ] 한국어·영어 같은 소식 묶기 (제목 유사도로는 안 잡힘, 큐레이터 단계에서 판단할지 결정)
