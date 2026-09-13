"""중복 제거: 링크가 같으면 하나로, 뉴스 제목이 비슷하면 대표 1건 + 함께 보도한 곳 목록으로 묶는다.

MCP·스킬은 이름이 비슷해도 다른 도구일 수 있어 링크 중복만 제거한다.
"""
import re
from difflib import SequenceMatcher

# 대표를 고를 때 우선순위. 공식 발표 > 매체 > 커뮤니티 (items.source_tier와 같은 값)
SOURCE_TIER = {
    "openai": 1, "google_ai": 1, "anthropic_skills": 1, "mcp_registry": 1,
    "aitimes": 2, "techcrunch_ai": 2, "venturebeat_ai": 2,
    "geeknews": 3, "hackernews": 3, "reddit_localllama": 3,
}
TITLE_SIMILARITY = 0.85
WORD = re.compile(r"[\w가-힣]+")


def title_key(title: str) -> str:
    return " ".join(WORD.findall(title.lower()))


def _rank(item: dict) -> tuple:
    return SOURCE_TIER.get(item["source"], 9), item["published_at"]


def dedupe(items: list[dict]) -> list[dict]:
    """입력은 normalize를 거친 항목. 출력 항목에는 also_reported_by [{source, url}]가 붙는다."""
    by_url: dict[str, dict] = {}
    for item in sorted(items, key=_rank):
        if item["url"] in by_url:
            by_url[item["url"]]["also_reported_by"].append({"source": item["source"], "url": item["url"]})
        else:
            by_url[item["url"]] = {**item, "also_reported_by": []}

    groups: list[dict] = []
    keys: list[str] = []
    for item in by_url.values():  # 이미 우선순위 순서라 먼저 들어온 쪽이 대표가 된다
        if item["type"] == "news":
            key = title_key(item["title"])
            match = next((i for i, k in enumerate(keys)
                          if k and groups[i]["type"] == "news" and SequenceMatcher(None, key, k).ratio() >= TITLE_SIMILARITY), None)
            if match is not None:
                groups[match]["also_reported_by"].append({"source": item["source"], "url": item["url"]})
                groups[match]["also_reported_by"].extend(item["also_reported_by"])
                continue
            keys.append(key)
        else:
            keys.append("")
        groups.append(item)
    return groups
