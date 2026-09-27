"""카드의 "이 카드인 이유"(why_this_card)를 데이터 근거로 만든다 (2026-09-27 발송 메일 점검).

큐레이터 모델이 쓴 이유는 "~에 관심 있는 개발자에게 유용한 도구입니다"처럼 어느 카드에나 붙는 문장이 많았고,
프롬프트로 막아도 로컬 모델이 따르지 않았다. 되돌림으로 바꿔 넣은 도구는 "○○ 설치 실패 후 대체합니다"처럼
내부 사정이 그대로 나갔다. 그래서 카드에는 사실인 근거(가중치가 양수인 관심 주제, 제목·설명에 나온 쓰는 도구)를 적고,
모델이 쓴 이유는 pick_why로 트레이스에만 남긴다. 근거가 하나도 없을 때만 모델 이유를 쓴다.
"""
import re

from agent.schemas import TOPICS

MAX_CHARS = 120  # schemas.Card.why_this_card 상한


def tools_mentioned(item: dict, tags: list[str]) -> list[str]:
    """제목·설명에 단어로 나온 쓰는 도구 태그 (대소문자 무시, 다른 단어의 일부는 제외)."""
    text = f"{item.get('title', '')} {item.get('summary') or item.get('description') or ''}".lower()
    return [tag for tag in tags if tag and re.search(rf"(?<![a-z0-9]){re.escape(tag.lower())}(?![a-z0-9])", text)]


def build(item: dict, memory: dict, model_why: str | None) -> str:
    parts = []
    topic = item.get("topic")
    weight = (memory.get("weights") or {}).get(topic, 0)
    if topic in TOPICS and weight > 0:
        parts.append(f"관심 주제 '{TOPICS[topic]}' 관심도 {weight}")
    tags = tools_mentioned(item, (memory.get("profile") or {}).get("tools_tags") or [])
    if tags:
        parts.append(f"쓰는 도구 {', '.join(tags[:3])} 관련")
    if parts:
        return " · ".join(parts)[:MAX_CHARS]
    if model_why:
        return model_why[:MAX_CHARS]
    return f"오늘 선별된 '{TOPICS.get(topic, 'AI')}' 항목"[:MAX_CHARS]


def attach(items: list[dict], memory: dict) -> list[dict]:
    """모델 이유는 pick_why로 옮기고 why를 근거로 바꾼다."""
    return [item | {"pick_why": item.get("why"), "why": build(item, memory, item.get("why"))} for item in items]
