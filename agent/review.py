"""선별 2차 검토 (2026-10-16 사용자 "정밀도 올려 어떠한 방법을 써서라도", 자동 추천으로 진행).

1차 선별(curator.select)을 통과한 뉴스만 엄격한 기준으로 한 번 더 판정해, 새로 일어난 일이 아닌 뉴스를 뺀다. 도구(MCP·스킬)는 보지 않는다.
- 실험(같은 선별 입력을 Haiku 5.5로 다시 판정, 정답은 tests/golden): 1차만이면 10/8~10/11 정밀도 84.9%·재현율 96.9%,
  2차 검토를 붙이면 93.1%·92.1%. 기준을 고치는 데 쓰지 않은 10/2~10/4는 85.1%·93.5% → 90.5%·88.0%
  (같은 날 이전 프롬프트는 72.0%·95.1%). 2차 기준이 "둘 다 아니면 빼기"면 재현율이 84%로 떨어져 "1차 판정 유지"로 했다
- 1단계는 재현율이 높게(넓게) 고르고 2단계가 정밀도를 맡는다. 20건 묶음이라 하루 4~5번 더 부른다
- 형식이 끝내 틀리거나 모델 장애면 1차 판정을 그대로 둔다(그 묶음은 빼지 않음). 실패는 큐레이터 형식 실패로 세지 않고 따로 센다
"""
import models
from agent import schemas, structured
from agent.structured import Stats

ROLE = "curator"
BATCH = 20
PROMPT = """너는 toolscout 큐레이터의 2차 검토자다. 아래 뉴스는 1차 선별에서 "AI 관련이고 오늘 볼 만함"으로 통과했다.
AI 에이전트를 만드는 개발자가 오늘 아침 브리핑에서 꼭 알아야 할 "새로 일어난 일"인지 다시 판정해 keep을 정한다.
1) 먼저 이 중 하나면 keep false: 사람의 발언·인터뷰·경고·해명·반박·주장이 중심인 기사(그 발언이 곧 정책·결정 발표면 제외),
  전망·분석·논평·"~할까?"·"~의 의미" 같은 해설 글, 기업이 AI를 써서 효과를 봤다는 고객·도입 사례,
  주요 AI 기업이 아닌 회사끼리의 업무협약(MOU)·협력 동맹, CEO 보수·인물 이야기,
  개인이 자기 GPU·PC에서 모델 속도·컨텍스트·벤치마크를 재 보거나 장비를 꾸민 글, 하드웨어 단종·가격 소식,
  재미로 만든 개인 데모·게임·실험·작품 소개(Show HN·Show GN이어도), 남이 만든 모델을 써 본 후기,
  AI가 곁다리로만 나오는 사회·문화·지역·법원·정치 기사, AI와 직접 관련 없는 일반 개발 도구·기업·하드웨어 소식
2) 아니면 이것일 때 keep true: 새 모델·도구·제품·기능 출시와 공개, 논문·연구 결과·벤치마크 순위 발표,
  개발자가 자기 일에 바로 쓸 수 있게 공개한 오픈소스 도구·라이브러리·앱·모델(개인이 Show HN·GitHub·Hugging Face에 올린 것도),
  오픈소스 프로젝트의 새 기능·지원 추가, 보도로 드러난 AI 기업의 사건·사고·조사·철회·소송, 규제·정책 결정,
  AI 기업의 투자·인수·실적, 주요 AI 기업(OpenAI·Anthropic·Google·Meta·Microsoft·Nvidia 등)의 계약·제휴
3) 둘 다 아니면 1차 판정을 믿고 keep true
입력의 모든 id를 빠짐없이 한 번씩 판정한다. reason은 한국어 한 줄(40자 이내).
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식: {"reviews": [{"id": 1, "keep": true, "reason": "..."}]}"""


async def run(selected: list[dict], reused: set[str], stats: Stats, model_call=None, judged: list[dict] | None = None) -> tuple[list[dict], dict]:
    """반환: (남긴 항목, 보고 {asked, dropped, failed}). reused(오늘·어제 판정을 쓴 뉴스 링크)는 이미 검토를 거쳤으므로 다시 보지 않는다.
    judged가 있으면 뺀 뉴스의 worth_today를 false로 바꿔 select_memo에 최종 판정이 남게 한다."""
    targets = [i for i, item in enumerate(selected) if item["type"] == "news" and item.get("url") not in reused]
    own = Stats()  # 검토 실패는 큐레이터 형식 실패(format_failed)로 세지 않는다. 호출·토큰만 합친다
    dropped: dict[int, str] = {}
    for start in range(0, len(targets), BATCH):
        batch = targets[start:start + BATCH]

        def ids_complete(parsed: schemas.ReviewBatch, size=len(batch)):
            if sorted(r.id for r in parsed.reviews) != list(range(1, size + 1)):
                raise ValueError(f"id가 1~{size}를 한 번씩 덮지 않음")

        payload = [{"id": n, "source": selected[i]["source"], "title": selected[i]["title"],
                    "summary": (selected[i].get("summary") or "")[:200]} for n, i in enumerate(batch, 1)]
        try:
            parsed = await structured.ask_json(ROLE, PROMPT, payload, schemas.ReviewBatch, own, ids_complete,
                                               f"2차 검토 {start // BATCH + 1}묶음", model_call)
        except models.ModelUnavailable:
            own.unrecovered += 1
            continue
        for review in parsed.reviews if parsed else []:
            if not review.keep:
                dropped[batch[review.id - 1]] = review.reason
    stats.calls += own.calls
    stats.input_tokens += own.input_tokens
    stats.output_tokens += own.output_tokens
    gone = {selected[i]["url"]: reason for i, reason in dropped.items() if selected[i].get("url")}
    for row in judged or []:
        if row.get("url") in gone:
            row.update(worth_today=False, reason=f"2차 검토: {gone[row['url']]}"[:200])
    kept = [item for i, item in enumerate(selected) if i not in dropped]
    return kept, {"asked": len(targets), "dropped": len(dropped), "failed": own.unrecovered,
                  "dropped_titles": [selected[i]["title"] for i in sorted(dropped)]}
