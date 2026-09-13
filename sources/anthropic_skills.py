"""anthropics/skills 저장소 커밋 (계획안 9.1 [확인됨]). GITHUB_TOKEN이 있으면 붙인다 (없으면 시간당 60회)."""
import os
from datetime import datetime

import httpx

from sources.common import SourceResult, error_text, make_item, parse_date

URL = "https://api.github.com/repos/anthropics/skills/commits"


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
        result.items.append(make_item(title=title, url=commit["html_url"], published=published,
                                      summary=body.strip()[:500], source="anthropic_skills", type="skill"))
    return result
