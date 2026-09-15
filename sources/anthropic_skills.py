"""anthropics/skills 저장소 커밋 (계획안 9.1 [확인됨]). GITHUB_TOKEN이 있으면 붙인다 (없으면 시간당 60회)."""
import os
import re
from datetime import datetime

import httpx

from sources.common import SourceResult, error_text, make_item, parse_date

URL = "https://api.github.com/repos/anthropics/skills/commits"
SKILL_FILE = re.compile(r"^(skills/[^/]+)/SKILL\.md$")


def changed_skill(sha: str, client: httpx.Client, headers: dict) -> str | None:
    """커밋이 바꾼 파일 중 skills/<이름>/SKILL.md가 있으면 그 폴더의 GitHub 주소. 못 찾으면 None (세션 8)."""
    try:
        response = client.get(f"{URL}/{sha}", headers=headers)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    for changed in response.json().get("files", []):
        if match := SKILL_FILE.match(changed.get("filename", "")):
            return f"https://github.com/anthropics/skills/tree/main/{match.group(1)}"
    return None


def fetch(since: datetime, client: httpx.Client) -> SourceResult:
    result = SourceResult("anthropic_skills")
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    params = {"since": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "per_page": 100}
    try:
        response = client.get(URL, params=params, headers=headers)
        response.raise_for_status()
        commits = response.json()
    except Exception as exc:
        result.error = error_text(exc)
        return result
    result.fetched = len(commits)
    for commit in commits:
        message = commit["commit"]["message"]
        published = parse_date(commit["commit"]["committer"]["date"])
        if published is None:
            continue
        title, _, body = message.partition("\n")
        item = make_item(title=title, url=commit["html_url"], published=published,
                         summary=body.strip()[:500], source="anthropic_skills", type="skill")
        if skill_url := changed_skill(commit["sha"], client, headers):
            item["skill_url"] = skill_url  # 검증관 read_skill이 읽을 SKILL.md 폴더 (세션 8)
        result.items.append(item)
    return result
