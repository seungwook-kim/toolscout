"""검증 노드 (계획안 부록 B 5, 예외 처리 표). 해설가 카드의 형식·글자 수·근거 링크·한글 비율을 규칙으로 확인한다.

- 형식·글자 수: agent/schemas.py의 Card 규격 (summary_ko 120자, for_me 150자·한 문장, 장단점 각 3개)
- 근거 링크: 장단점마다 evidence_url이 있고 카드 링크와 같아야 한다
- 한글 비율: 요약·for_me·장단점을 어절로 나눠 한글이 든 어절이 60% 이상. 글자 단위로 세면
  제품명이 많은 정상 요약도 떨어져서(예: 54%) 어절 기준으로 정했다
- 실패하면 이유를 붙여 해설가를 1회 다시 부른다. 그래도 실패면 그 카드는 빼고 트레이스에 이유를 남긴다
모델은 부르지 않는다 (재시도만 해설가 호출).
"""
import re
from typing import Awaitable, Callable

from pydantic import ValidationError

from agent import schemas, tracing

MIN_HANGUL_RATIO = 0.6
HANGUL = re.compile(r"[가-힣]")
LETTER = re.compile(r"[가-힣A-Za-z]")
NEXT_SENTENCE = re.compile(r"[.!?。]\s+\S")

Redo = Callable[[dict, str], Awaitable[dict]]


def hangul_ratio(text: str) -> float:
    """글자가 든 어절 중 한글이 든 어절의 비율. 글자가 없으면 0."""
    words = [w for w in text.split() if LETTER.search(w)]
    return sum(1 for w in words if HANGUL.search(w)) / len(words) if words else 0.0


def card_text(card: schemas.Card) -> str:
    return " ".join([card.summary_ko, card.for_me, *(p.text for p in card.pros + card.cons)])


def problems(card: dict) -> list[str]:
    """카드 하나의 문제 목록. 비어 있으면 통과."""
    try:
        parsed = schemas.Card.model_validate(card)
    except ValidationError as exc:
        return [f"형식 {'.'.join(map(str, e['loc'])) or '전체'}: {e['msg']}" for e in exc.errors()[:3]]
    found = []
    if NEXT_SENTENCE.search(parsed.for_me.strip()):
        found.append("for_me가 한 문장이 아니다")
    if any(p.evidence_url != parsed.url for p in parsed.pros + parsed.cons):
        found.append("장단점 근거 링크가 카드 링크와 다르다")
    ratio = hangul_ratio(card_text(parsed))
    if ratio < MIN_HANGUL_RATIO:
        found.append(f"한글 비율 {ratio:.0%} (기준 {MIN_HANGUL_RATIO:.0%})")
    return found


async def run_user(explained: dict, items_by_url: dict[str, dict], redo: Redo) -> dict:
    """해설가 결과(explainer.explain_user) 한 사용자분을 검사한다. redo(item, 이유)는 해설가 재호출.

    반환: {user_id, cards(순위 다시 매김), excluded[{title, url, reasons}], retried, rejected, format_failed, model_failed}
    """
    kept, excluded, retried = [], [], 0
    with tracing.span("validate", kind="chain", input={"user_id": explained["user_id"], "cards": len(explained["cards"])}) as span:
        for card in explained["cards"]:
            reasons = problems(card)
            if not reasons:
                kept.append(card)
                continue
            retried += 1
            outcome = await redo(items_by_url[card["url"]], "; ".join(reasons))
            if outcome["status"] == "card":
                reasons = problems(outcome["card"])
                if not reasons:
                    kept.append(outcome["card"])
                    continue
            else:
                reasons = [*reasons, f"재시도 결과 {outcome['status']}: {outcome.get('reason') or '형식 실패'}"]
            excluded.append({"title": card["title"], "url": card["url"], "reasons": reasons})
        cards = [card | {"rank": rank} for rank, card in enumerate(kept, 1)]
        span.update(output={"kept": len(cards), "retried": retried, "excluded": excluded},
                    level="WARNING" if excluded else "DEFAULT")
    return {"user_id": explained["user_id"], "cards": cards, "excluded": excluded, "retried": retried,
            "rejected": explained["rejected"], "format_failed": explained["format_failed"],
            "model_failed": explained.get("model_failed", [])}
