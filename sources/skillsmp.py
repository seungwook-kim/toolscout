"""SkillsMP 스킬 목록 (계획안 9.1 [측정예정] 2차 테스트, 2026-09-23 붙임).

검색만 열려 있어(`/api/v1/skills/search`, q 필수) 주제어 목록으로 나눠 훑고 githubUrl로 합친다.
응답의 updatedAt은 실제 갱신 시각이 아니라 SkillsMP가 긁어 간 시각이라(2026-09-23 실측: 같은 날 받은 319건이 모두 4~5일 전)
7일 창으로는 신규를 가릴 수 없다. 그래서 items에 없는 것만 새 항목으로 본다. DB를 못 읽으면 거르지 않고 그대로 넘긴다.
MCP 레지스트리와 같은 방식으로 게시자당 3건, 별 수 상위 20건까지만 큐레이터에 올린다.
키(SKILLSMP_API_KEY)가 없으면 건너뛴다. 무료 키 하루 500회 기준이라 한 번 실행에 주제어 수만큼만 부른다.
"""
import os
from datetime import datetime, timezone

import httpx

from sources.common import SourceResult, error_text, make_item

URL = "https://skillsmp.com/api/v1/skills/search"
QUERIES = ("mcp", "agent", "claude", "automation", "data", "code", "document", "research")
PAGE_LIMIT, MAX_PER_PUBLISHER, MAX_NEW = 50, 3, 20


def known_urls(urls: list[str]) -> set[str]:
    """이미 도구 목록에 있는 주소. DB를 못 읽으면 빈 집합(거르지 않는다)."""
    if not urls:
        return set()
    try:
        from sqlalchemy import select

        import db

        with db.get_engine().connect() as connection:
            return {row[0] for row in connection.execute(select(db.Item.url).where(db.Item.url.in_(urls)))}
    except Exception:
        return set()


def fetch(client: httpx.Client) -> SourceResult:
    result = SourceResult("skillsmp")
    key = os.environ.get("SKILLSMP_API_KEY", "").strip()
    if not key:
        result.stats = {"건너뜀": "SKILLSMP_API_KEY 없음"}
        return result
    headers = {"Authorization": f"Bearer {key}"}
    found: dict[str, dict] = {}
    failed = []
    for query in QUERIES:
        try:
            response = client.get(URL, params={"q": query, "limit": PAGE_LIMIT, "sortBy": "recent"}, headers=headers)
            response.raise_for_status()
            skills = response.json().get("data", {}).get("skills", [])
        except Exception as exc:
            failed.append(f"{query}: {error_text(exc)}")
            continue
        for skill in skills:
            if skill.get("githubUrl"):
                found[skill["githubUrl"]] = skill
    if failed and not found:
        result.error = failed[0]
        return result
    result.fetched = len(found)

    fresh = [s for url, s in found.items() if url not in known_urls(list(found))]
    fresh.sort(key=lambda s: -(s.get("stars") or 0))
    picked, per_publisher = [], {}
    for skill in fresh:
        author = skill.get("author") or "?"
        if per_publisher.get(author, 0) >= MAX_PER_PUBLISHER:
            continue
        per_publisher[author] = per_publisher.get(author, 0) + 1
        picked.append(skill)
        if len(picked) >= MAX_NEW:
            break
    for skill in picked:
        published = datetime.fromtimestamp(skill.get("updatedAt") or 0, timezone.utc)
        item = make_item(title=f"{skill.get('name', '')} ({skill.get('author', '')})", url=skill["githubUrl"],
                         published=published, summary=skill.get("description", ""), source="skillsmp", type="skill")
        item["skill_url"] = skill["githubUrl"]  # 검증관 read_skill이 읽을 SKILL.md 폴더
        item["stars"] = skill.get("stars")
        result.items.append(item)
    result.stats = {"주제어": len(QUERIES), "받은_서로_다른_스킬": len(found), "이미_본_것_제외": len(fresh),
                    "올린_것": len(result.items), "실패한_주제어": failed}
    return result
