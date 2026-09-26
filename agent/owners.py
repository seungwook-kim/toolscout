"""도구 후보의 게시자 반복 줄이기 (2026-09-26 발송분 점검).

같은 게시자(fuxicodex)의 스킬이 9/24·9/25 이틀에 4장 나갔다. 수집 단계의 게시자당 3건 제한은 하루 안에서만 걸려
날짜를 넘긴 반복을 막지 못했다. 사용자별 도구 후보에서 GitHub 게시자(저장소 주인)를 기준으로
- 최근 RECENT_DAYS일 안에 이 사용자에게 카드로 나간 게시자의 도구는 뺀다
- 남은 것 중 같은 게시자는 하루 한 건(후보 순서상 앞의 것)만 둔다
GitHub 주소가 아닌 도구(원격 주소만 있는 MCP 등)는 게시자를 모르니 그대로 둔다.
"""
import re

RECENT_DAYS = 7
_OWNER = re.compile(r"^https?://(?:www\.)?github\.com/([^/?#]+)", re.I)


def owner(url: str | None) -> str | None:
    match = _OWNER.match(url or "")
    return match.group(1).lower() if match else None


def spread(tools: list[dict], recent_urls: list[str]) -> tuple[list[dict], int]:
    """반환: (남긴 도구, 뺀 수). tools는 후보 순서대로 들어온다."""
    recent = {o for o in map(owner, recent_urls) if o}
    kept, used = [], set()
    for item in tools:
        name = owner(item.get("url"))
        if name and (name in recent or name in used):
            continue
        if name:
            used.add(name)
        kept.append(item)
    return kept, len(tools) - len(kept)
