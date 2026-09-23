"""같은 소식 겹침 빼기 (2026-09-23 사용자 요청, pipeline/README 할 일 "한국어·영어 같은 소식 묶기").

제목 유사도(pipeline/dedupe.py)는 언어가 다르면 못 잡는다. 9/23 수집에서도 GPT-6 Sol·Luna가 영문·한국어로 4건 들어왔고,
본인 뉴스 5장 중 2장이 같은 소식이 됐다. 후보 단계 프롬프트에 "하나만"을 적어도 로컬 모델이 지키지 않아,
고른 뉴스만 따로 보여 주고 "같은 사건끼리 묶기"만 묻는다. 묶음마다 앞(중요 순) 하나만 남기고 빈 자리는 채우지 않는다
(예비를 같이 고르게 하자 로컬 모델이 뉴스를 3장만 고르고 예비는 비웠다).
모델은 해설가 순서를 빌려 쓴다(개발 모드 Groq qwen3.8-27b부터, 운영 Sonnet 5부터). 9/23 실측에서 로컬 gemma3:12b는
이름만 같은 다른 소식(뮤즈 보안 결함·뮤즈 표절 인정)을 묶어 5건 중 3건을 잘못 뺐고, qwen3.8-27b는 잘못 뺀 것이 없었다.
공개 뉴스 제목만 보낸다. 모델 장애·형식 실패면 고른 그대로 둔다 (브리핑을 막지 않는다).
"""
import models
from agent import schemas, structured
from agent.structured import Stats

MODEL_ROLE = "explainer"
PROMPT = """너는 toolscout 큐레이터다. 뉴스 제목 목록에서 같은 발표·같은 출시·같은 사건을 다룬 것끼리 묶는다.
- 기준: 한 기사를 읽으면 다른 기사는 안 읽어도 될 만큼 같은 내용일 때만 묶는다. 언어·매체·제목 표현은 상관없다
  (예: 영문 공식 발표와 그 소식을 전한 한국어 기사는 묶는다)
- 같은 모델 이름이 나와도 다루는 일이 다르면 묶지 않는다. 모델 출시 / 그 모델을 쓴 회사 사례 / 그 모델의 새 기능·가격 / 성능 분석은 서로 다른 소식이다
- 애매하면 묶지 않는다
- 2건 이상인 묶음만 쓴다. 겹치는 게 없으면 빈 목록
출력은 JSON 객체 하나만 쓴다. 설명 문장이나 코드 블록을 붙이지 않는다. 형식: {"groups": [[1, 3]]}"""


async def groups(items: list[dict], stats: Stats, model_call=None, label: str = "같은 소식 묶기") -> list[list[int]] | None:
    """items 제목을 같은 소식끼리 묶는다. 반환: 2건 이상 묶음의 1부터 센 번호 목록, 모델 장애·형식 실패면 None."""
    def ids_valid(parsed: schemas.SameStory):
        flat = [i for group in parsed.groups for i in group]
        if len(set(flat)) != len(flat) or any(not 1 <= i <= len(items) for i in flat):
            raise ValueError("묶음 id가 범위 밖이거나 두 묶음에 들어감")

    call = model_call or (lambda _role, messages, tools=None: models.call(MODEL_ROLE, messages, tools, temperature=0))
    try:
        parsed = await structured.ask_json("curator", PROMPT, [{"id": n, "title": i["title"]} for n, i in enumerate(items, 1)],
                                           schemas.SameStory, stats, ids_valid, label, call)
    except models.ModelUnavailable as exc:
        stats.model_failed(label, exc)
        return None
    return [sorted(g) for g in parsed.groups if len(g) > 1] if parsed else None


async def drop(picks: list[dict], stats: Stats, model_call=None) -> tuple[list[dict], int]:
    """picks(중요 순)에서 같은 소식을 묶어 묶음마다 앞 하나만 남긴다. 반환: (남긴 뉴스, 뺀 건수)."""
    if len(picks) < 2:
        return picks, 0
    found = await groups(picks, stats, model_call)
    later = {i for group in found or [] for i in group[1:]}  # 묶음에서 앞 번호 하나만 남긴다
    return [item for n, item in enumerate(picks, 1) if n not in later], len(later)
