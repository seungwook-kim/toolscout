"""행사·책 홍보처럼 새 소식이 아닌 연재·홍보 뉴스를 모델에 보내기 전에 뺀다 (2026-09-27 사용자 결정 "걸러").

9/23 "[AI리더의 서가]"(책 소개), 9/26 "TechCrunch Disrupt 2026: ..."(행사 세션 예고)가 뉴스 칸에 나갔다.
대부분은 선별 프롬프트의 worth_today 기준이 거르고, 여기서는 제목 형식만으로 확실한 것만 좁게 잡는다.
- TechCrunch는 자기 행사(Disrupt·TC Sessions·StrictlyVC) 티켓 할인·연사·세션 홍보 글을 뉴스 피드에 섞는다.
  9/27 0시 48시간 후보 152건 중 5건. 행사 이름이 있으면 홍보로 보되, 그 자리의 실제 발표(launch·unveil 등)는 남긴다
- "개최"·"행사" 같은 넓은 단어는 진짜 소식도 걸려서 넣지 않는다 (9/26 저장 뉴스 91건 중 SKT 회의 개최 기사)
"""
import re

EVENT = "행사 홍보"
PATTERNS = {
    "책 소개 연재": re.compile(r"^\s*\[(?:AI리더의 서가|서평|신간|북리뷰|책 ?소개)\]"),
    EVENT: re.compile(r"\b(?:TechCrunch Disrupt|TC Sessions|StrictlyVC)\b", re.I),
    "웨비나 안내": re.compile(r"웨비나|\bwebinar\b", re.I),
}
ANNOUNCED = re.compile(r"\b(?:launch(?:es|ed)?|unveil(?:s|ed)?|announce(?:s|d)?|debut(?:s|ed)?|release(?:s|d)?)\b|공개|출시|발표", re.I)


def reason(item: dict) -> str | None:
    if item.get("type") != "news":
        return None
    title = item.get("title") or ""
    name = next((name for name, pattern in PATTERNS.items() if pattern.search(title)), None)
    return None if name == EVENT and ANNOUNCED.search(title) else name


def drop(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """반환: (남긴 항목, 뺀 항목 [{title, reason}])."""
    kept, dropped = [], []
    for item in items:
        why = reason(item)
        if why:
            dropped.append({"title": item["title"], "reason": why})
        else:
            kept.append(item)
    return kept, dropped
