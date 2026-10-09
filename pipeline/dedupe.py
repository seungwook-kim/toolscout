"""중복 제거: 링크가 같으면 하나로, 뉴스 제목이 비슷하면 대표 1건 + 함께 보도한 곳 목록으로 묶는다.

MCP·스킬은 이름이 비슷해도 다른 도구일 수 있어 제목으로 묶지 않는다. MCP는 링크가 아니라 이름으로 중복을 판단한다.
"""
import re
from difflib import SequenceMatcher

# 대표를 고를 때 우선순위. 공식 발표 > 매체 > 커뮤니티 (items.source_tier와 같은 값)
SOURCE_TIER = {
    "openai": 1, "google_ai": 1, "claude_notes": 1, "anthropic_skills": 1, "mcp_registry": 1,
    "aitimes": 2, "techcrunch_ai": 2, "github_search": 2,
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
    # 레지스트리 MCP의 저장소 주소 → 그 항목의 키. GitHub 검색으로 들어온 같은 저장소를 레지스트리 항목에 합치려고 (대소문자 무시)
    registry_keys = {item["url"].lower(): f"mcp:{item['title']}" for item in items
                     if item["type"] == "mcp" and item["source"] == "mcp_registry"}
    for item in sorted(items, key=_rank):
        # 레지스트리에서는 다른 서버가 같은 저장소·웹사이트 링크를 공유하므로 MCP는 이름(제목)으로 구분한다
        key = f"mcp:{item['title']}" if item["type"] == "mcp" else item["url"]
        if item["type"] == "mcp" and item["source"] == "github_search":
            # GitHub 검색 항목은 제목에 버전이 없어 이름이 레지스트리와 다르다. 주소가 같으면 레지스트리(설치 정보가 있는 쪽)가 대표가 된다
            key = registry_keys.get(item["url"].lower(), f"gh:{item['url'].lower()}")
        if key in by_url:
            by_url[key]["also_reported_by"].append({"source": item["source"], "url": item["url"]})
        else:
            by_url[key] = {**item, "also_reported_by": []}

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
