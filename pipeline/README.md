# pipeline/

수집 항목 정리와 중복 제거. 상태: 구현 (계획안 9.2 W1, 부록 B 1번).

## 파일
- `normalize.py`: HTML·엔티티 제거, 공백 정리, URL 정규화(추적 파라미터·# 제거)
- `dedupe.py`: 링크 중복 제거(MCP는 이름 기준), 뉴스 제목 유사도 0.85 이상 묶기, 대표는 공식 > 매체 > 커뮤니티

## 들어오고 나가는 데이터
- 들어옴: `sources/`의 항목 `{title, url, published_at, summary, source, type}`
- 나감: 같은 모양 + `also_reported_by [{source, url}]` (대표 1건 + 함께 보도한 곳)

## 관련
- `agent/`: 큐레이터가 이 출력을 받아 선별한다
- `tests/pipeline/run_dedupe.py`: 오늘 데이터 전후 건수

## 할 일
- [ ] 한국어·영어 같은 소식 묶기 (제목 유사도로는 안 잡힘, 큐레이터 단계에서 판단할지 결정)
- [ ] `SOURCE_TIER`를 items.source_tier 저장과 연결
- [ ] 수집량 기준 결정 후 반영 (필터 후 912~943건, 대부분 MCP 신규 등록)
