"""검증 노드 (계획안 부록 B 5, 예외 처리 표). 해설가 초안 카드의 형식·글자 수·근거 링크·한글 비율·관련도를 규칙으로 확인한다.

두 단계 (2026-09-15 사용자 결정)
1. 자동 고침: 요약이 120자를 넘으면 120자 안의 마지막 문장 끝에서 잘라 통과시킨다. 문장 끝이 없으면 2단계로
2. 자가 수정: 빈 필드·남은 문제는 이유를 해설가에게 돌려 1회 다시 쓰게 한다. 그래도 문제면 카드를 빼고 트레이스에 이유

검사 항목
- 형식·글자 수: agent/schemas.py의 Card 규격 (summary_ko 120자, for_me 150자·한 문장, 장단점 각 3개, 관련도 3~5)
- 근거 링크: 장단점마다 evidence_url이 있고 카드 링크와 같아야 한다
- 한글 비율: 요약·for_me·장단점을 어절로 나눠 한글이 든 어절이 60% 이상. 글자 단위로 세면
  제품명이 많은 정상 요약도 떨어져서(예: 54%) 어절 기준으로 정했다
모델은 부르지 않는다 (2단계 재시도만 해설가 호출).
"""
import re
from typing import Awaitable, Callable

from pydantic import ValidationError

from agent import schemas, tracing

MIN_HANGUL_RATIO = 0.6
HANGUL = re.compile(r"[가-힣]")
LETTER = re.compile(r"[가-힣A-Za-z]")
NEXT_SENTENCE = re.compile(r"[.!?。]\s+\S")
SENTENCE_END = re.compile(r"[.!?。]")
EMPTY_FIX = "summary_ko와 for_me는 빈 값이나 null 없이 내용을 채운다. 이 사용자와 이어지지 않으면 reject를 true로 쓴다"

Redo = Callable[[dict, str], Awaitable[dict]]


def hangul_ratio(text: str) -> float:
    """글자가 든 어절 중 한글이 든 어절의 비율. 글자가 없으면 0."""
    words = [w for w in text.split() if LETTER.search(w)]
    return sum(1 for w in words if HANGUL.search(w)) / len(words) if words else 0.0


def fit_summary(text: str, limit: int = schemas.MAX_SUMMARY) -> tuple[str, str | None]:
    """1단계. 반환: (요약, 고친 내용). limit을 넘으면 limit 안의 마지막 문장 끝에서 자른다. 문장 끝이 없으면 그대로 둔다."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text, None
    ends = [m.end() for m in SENTENCE_END.finditer(text)
            if m.end() <= limit and (m.end() == len(text) or text[m.end()].isspace())]
    if not ends:
        return text, None
    cut = text[:ends[-1]].strip()
    return cut, f"요약 {len(text)}자 → 문장 끝에서 {len(cut)}자로 자름"


def autofix(card: dict) -> tuple[dict, list[str]]:
    summary, fix = fit_summary(card.get("summary_ko") or "")
    return (card | {"summary_ko": summary}, [fix]) if fix else (card, [])


def card_text(card: schemas.Card) -> str:
    return " ".join([card.summary_ko, card.for_me, *(p.text for p in card.pros + card.cons)])


def problems(card: dict) -> list[str]:
    """카드 하나의 문제 목록. 비어 있으면 통과."""
    empty = [f for f in ("summary_ko", "for_me") if not (card.get(f) or "").strip()]
    if empty:
        return [f"{'·'.join(empty)}이 비었다. {EMPTY_FIX}"]
    if card.get("relevance") is None:
        return ["relevance(1~5)가 비었다. 이 사용자와의 관련도를 정수로 쓴다"]
    try:
        parsed = schemas.Card.model_validate(card)
    except ValidationError as exc:
        return [_field_problem(e) for e in exc.errors()[:3]]
    found = []
    if NEXT_SENTENCE.search(parsed.for_me.strip()):
        found.append("for_me가 한 문장이 아니다")
    if any(p.evidence_url != parsed.url for p in parsed.pros + parsed.cons):
        found.append("장단점 근거 링크가 카드 링크와 다르다")
    ratio = hangul_ratio(card_text(parsed))
    if ratio < MIN_HANGUL_RATIO:
        found.append(f"한글 비율 {ratio:.0%} (기준 {MIN_HANGUL_RATIO:.0%})")
    return found


def _field_problem(error: dict) -> str:
    field = ".".join(map(str, error["loc"])) or "전체"
    if field == "summary_ko" and error["type"] == "string_too_long":
        return f"summary_ko가 {schemas.MAX_SUMMARY}자를 넘고 그 안에 문장 끝이 없다. 두 문장 이하, {schemas.MAX_SUMMARY}자 이내로 쓴다"
    return f"형식 {field}: {error['msg']}"


async def run_user(explained: dict, items_by_url: dict[str, dict], redo: Redo) -> dict:
    """해설가 결과(explainer.explain_user) 한 사용자분을 검사한다. redo(item, 이유)는 해설가 재호출.

    반환: {user_id, cards(순위 다시 매김), excluded[{title, url, reasons}], fixed[{title, fixes}], retried,
           rejected, format_failed, model_failed}
    """
    kept, excluded, fixed, retried = [], [], [], 0
    rejected = list(explained["rejected"])
    with tracing.span("validate", kind="chain", input={"user_id": explained["user_id"], "cards": len(explained["cards"])}) as span:
        for draft in explained["cards"]:
            card, fixes = autofix(draft)
            reasons = problems(card)
            if not reasons:
                kept.append(card)
                if fixes:
                    fixed.append({"title": card["title"], "fixes": fixes})
                continue
            retried += 1
            outcome = await redo(items_by_url[card["url"]], "; ".join(reasons))
            if outcome["status"] == "card":
                card, fixes = autofix(outcome["card"])
                reasons = problems(card)
                if not reasons:
                    kept.append(card)
                    if fixes:
                        fixed.append({"title": card["title"], "fixes": fixes})
                    continue
            elif outcome["status"] == "rejected":  # 다시 쓰게 했더니 해설가가 반려(관련도 3 미만 포함)로 판단
                rejected.append({"title": card["title"], "url": card["url"], "reason": outcome["reason"]})
                continue
            else:
                reasons = [*reasons, f"재시도 결과 {outcome['status']}: {outcome.get('reason') or '형식 실패'}"]
            excluded.append({"title": card["title"], "url": card["url"], "reasons": reasons})
        cards = [card | {"rank": rank} for rank, card in enumerate(kept, 1)]
        span.update(output={"kept": len(cards), "retried": retried, "fixed": fixed, "excluded": excluded},
                    level="WARNING" if excluded else "DEFAULT")
    return {"user_id": explained["user_id"], "cards": cards, "excluded": excluded, "fixed": fixed, "retried": retried,
            "rejected": rejected, "format_failed": explained["format_failed"],
            "model_failed": explained.get("model_failed", [])}
