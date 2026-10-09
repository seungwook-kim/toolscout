"""GitHub 저장소 검색으로 새 MCP·스킬 후보 모으기 (2026-10-09 추가).

왜: 공식 MCP 레지스트리와 SkillsMP에 오르지 않은 새 저장소가 GitHub에는 매일 올라온다.
topic 검색(저장소 검색 API)으로 최근 7일(collect.TOOL_WINDOW) 안에 만든 저장소를 별 수 순으로 훑는다.

측정 (2026-10-09, 최근 7일 생성, 포크·보관 제외)
- topic:mcp-server 별 10+ 10개, topic:mcp 별 10+ 33개 / topic:claude-skills 별 30+ 14개, topic:agent-skills 별 30+ 19개,
  topic:claude-code-skills 별 30+ 0개. 쿼리마다 100개 안쪽이라 1페이지(최대 100)면 충분하다
- MCP는 별 10 이상(둘 합쳐 40개 안쪽), 스킬은 별 30 이상(30개 안쪽)으로 하루 후보가 수십 건 안쪽이 된다
- 스킬 토픽은 별 5 이상만 해도 87개(agent-skills)라 별 기준을 높였다. 검색 API는 분당 30회라 이 소스는 5회만 부른다

거르기
- 포크·보관(archived)·설명 없는 저장소는 뺀다
- 종류 판정 (한 저장소가 여러 토픽에 걸릴 때 하나로): 토픽에 mcp-server가 있으면 MCP, 아니면 스킬 토픽
  (claude-skills·agent-skills·claude-code-skills)이 있으면 스킬, 둘 다 없으면(mcp만) MCP.
  mcp는 클라이언트·문서에도 흔히 붙는 넓은 토픽이라 더 구체적인 토픽이 이기고, mcp-server는 "서버"를 직접 말하는 토픽이라 가장 앞선다
- 별 기준은 판정된 종류의 기준을 쓴다 (MCP 10 / 스킬 30)
- 게시자(owner)당 종류마다 최대 3건, 종류마다 별 수 상위 20건 (mcp_registry·skillsmp와 같은 방식)

설치 정보 (MCP만, 최종 후보에 대해서만)
- 저장소 루트 package.json(name과 bin이 있고 private이 아님) 또는 pyproject.toml([project].name과 [project.scripts])을 읽고,
  npm·PyPI에 같은 이름이 실제로 있고 그 패키지의 저장소 주소가 이 저장소를 가리킬 때만 install을 붙인다
  (남이 같은 이름을 먼저 올린 경우를 걸러낸다). 모양은 mcp_registry.install_info와 같다. 못 찾으면 install을 비워 두고,
  검증관이 README를 읽거나 "설치법 미확인"으로 멈춰 카드에 검증 예정/미확인이 그대로 보인다 (검증된 것처럼 보이지 않는다)
- 파일은 raw.githubusercontent.com에서 읽어 API 한도를 쓰지 않고, 토큰은 npm·PyPI·raw에 보내지 않는다

스킬은 저장소 루트의 SKILL.md를 skill_url로 둔다 (기본 브랜치 기준). 루트에 없으면 검증관 판독이 "원문 접근 불가"로 정직하게 남는다.
별 수는 검색 응답의 stargazers_count를 쓴다 (항목의 stars로 실려 persist.save_catalog가 items.stars에 저장).
GITHUB_TOKEN이 없으면 오류로 기록하고 건너뛴다. 토큰 값은 출력하지 않는다.
"""
import json
import os
import tomllib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from sources import github_stars
from sources.common import SourceResult, error_text, make_item, parse_date

NAME = "github_search"
URL = "https://api.github.com/search/repositories"
RAW = "https://raw.githubusercontent.com/{full_name}/HEAD/{path}"
NPM = "https://registry.npmjs.org/{name}/latest"
PYPI = "https://pypi.org/pypi/{name}/json"
PAGE_SIZE = 100
MCP_TOPICS, SKILL_TOPICS = ("mcp-server", "mcp"), ("claude-skills", "agent-skills", "claude-code-skills")
MIN_STARS = {"mcp": 10, "skill": 30}
MAX_PER_OWNER, TOP_PER_KIND = 3, 20
WORKERS = 8


def kind_of(topics: list[str]) -> str:
    """토픽으로 종류를 하나 고른다. 이유는 모듈 설명의 "종류 판정"."""
    names = {t.lower() for t in topics}
    if "mcp-server" in names:
        return "mcp"
    if names & set(SKILL_TOPICS):
        return "skill"
    return "mcp"


def _search(client: httpx.Client, token: str, topic: str, day: str, min_stars: int) -> list[dict]:
    query = f"topic:{topic} created:>={day} stars:>={min_stars} fork:false archived:false"
    response = client.get(URL, params={"q": query, "sort": "stars", "order": "desc", "per_page": PAGE_SIZE},
                          headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    response.raise_for_status()
    return response.json().get("items", [])


def _pick(repos: list[dict]) -> list[dict]:
    """한 종류 안에서 별 수 순으로 게시자당 3건, 상위 20건."""
    per_owner: dict[str, int] = {}
    picked = []
    for repo in sorted(repos, key=lambda r: r.get("stargazers_count") or 0, reverse=True):
        owner = ((repo.get("owner") or {}).get("login") or repo["full_name"].split("/")[0]).lower()
        if per_owner.get(owner, 0) >= MAX_PER_OWNER:
            continue
        per_owner[owner] = per_owner.get(owner, 0) + 1
        picked.append(repo)
        if len(picked) >= TOP_PER_KIND:
            break
    return picked


def _same_repo(text: str | None, full_name: str) -> bool:
    return full_name.lower() in (text or "").lower()


def _get_json(client: httpx.Client, url: str) -> dict | None:
    try:
        response = client.get(url)
        return response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _get_text(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
        return response.text if response.status_code == 200 else None
    except httpx.HTTPError:
        return None


def _npm_package(full_name: str, client: httpx.Client) -> dict | None:
    text = _get_text(client, RAW.format(full_name=full_name, path="package.json"))
    if not text:
        return None
    try:
        meta = json.loads(text)
    except ValueError:
        return None
    name = meta.get("name") if isinstance(meta, dict) else None
    if not name or meta.get("private") or not meta.get("bin"):
        return None
    latest = _get_json(client, NPM.format(name=quote(name, safe="@")))
    repository = (latest or {}).get("repository")
    repo_url = repository.get("url") if isinstance(repository, dict) else repository
    if not latest or latest.get("name") != name or not _same_repo(repo_url, full_name):
        return None
    return {"registryType": "npm", "identifier": name, "version": latest.get("version"), "transport": "stdio"}


def _pypi_package(full_name: str, client: httpx.Client) -> dict | None:
    text = _get_text(client, RAW.format(full_name=full_name, path="pyproject.toml"))
    if not text:
        return None
    try:
        project = tomllib.loads(text).get("project") or {}
    except tomllib.TOMLDecodeError:
        return None
    name = project.get("name")
    if not name or not project.get("scripts"):
        return None
    data = _get_json(client, PYPI.format(name=quote(name, safe="")))
    info = (data or {}).get("info") or {}
    links = [info.get("home_page"), *((info.get("project_urls") or {}).values())]
    if not info or not any(_same_repo(link, full_name) for link in links):
        return None
    return {"registryType": "pypi", "identifier": info.get("name") or name, "version": info.get("version"), "transport": "stdio"}


def install_info(full_name: str, client: httpx.Client) -> dict | None:
    """저장소 루트의 package.json·pyproject.toml로 실제 있는 npm·PyPI 패키지를 찾아 mcp_registry.install_info 모양으로."""
    packages = [p for p in (_npm_package(full_name, client), _pypi_package(full_name, client)) if p]
    return {"packages": packages} if packages else None


def fetch(since: datetime, client: httpx.Client, *, token: str | None = None) -> SourceResult:
    result = SourceResult(NAME)
    token = os.environ.get("GITHUB_TOKEN", "").strip() if token is None else token
    if not token:
        result.error = "GITHUB_TOKEN 없음"
        return result
    day = since.astimezone(timezone.utc).strftime("%Y-%m-%d")
    # 쿼리마다 그 토픽 쪽 종류의 별 기준으로 받고, 종류가 정해진 뒤 판정된 종류의 기준을 다시 적용한다
    queries = [(t, MIN_STARS["mcp"]) for t in MCP_TOPICS] + [(t, MIN_STARS["skill"]) for t in SKILL_TOPICS]
    found: dict[str, dict] = {}
    failed, per_query = [], {}
    for topic, min_stars in queries:
        try:
            repos = _search(client, token, topic, day, min_stars)
        except Exception as exc:
            failed.append(f"{topic}: {error_text(exc)}")
            continue
        per_query[topic] = len(repos)
        for repo in repos:
            found[repo["full_name"].lower()] = repo
    if failed and not found:
        result.error = failed[0]
        return result
    result.fetched = len(found)

    dropped = {"포크": 0, "보관": 0, "설명없음": 0, "창_밖": 0, "별_기준_미달": 0}
    by_kind: dict[str, list[dict]] = {"mcp": [], "skill": []}
    for repo in found.values():
        created = parse_date(repo.get("created_at"))
        if repo.get("fork"):
            dropped["포크"] += 1
        elif repo.get("archived"):
            dropped["보관"] += 1
        elif not (repo.get("description") or "").strip():
            dropped["설명없음"] += 1
        elif created is None or created < since:
            dropped["창_밖"] += 1  # 쿼리는 날짜 단위라 정확한 시각으로 한 번 더 거른다
        else:
            kind = kind_of(repo.get("topics") or [])
            if (repo.get("stargazers_count") or 0) < MIN_STARS[kind]:
                dropped["별_기준_미달"] += 1
            else:
                by_kind[kind].append(repo)
    picked = {kind: _pick(repos) for kind, repos in by_kind.items()}

    with ThreadPoolExecutor(WORKERS) as pool:
        installs = dict(zip((r["full_name"] for r in picked["mcp"]),
                            pool.map(lambda r: install_info(r["full_name"], client), picked["mcp"])))
    for kind in ("mcp", "skill"):
        for repo in picked[kind]:
            owner, name = repo["full_name"].split("/", 1)
            url = github_stars.repo_url((owner, name))  # mcp_registry와 같은 주소 모양 (겹치면 dedupe가 하나로)
            item = make_item(title=f"{name} ({owner})", url=url, published=parse_date(repo["created_at"]),
                             summary=repo["description"], source=NAME, type=kind)
            item["stars"] = repo.get("stargazers_count")
            if kind == "mcp" and (install := installs.get(repo["full_name"])):
                item["install"] = install
            elif kind == "skill":
                item["skill_url"] = f"{url}/tree/{repo.get('default_branch') or 'main'}"
            result.items.append(item)
    result.stats = {"창_시작일": day, "쿼리별_받은_수": per_query, "서로_다른_저장소": len(found), "제외": dropped,
                    "MCP_후보": len(picked["mcp"]), "스킬_후보": len(picked["skill"]),
                    "MCP_설치정보_붙음": sum(1 for v in installs.values() if v), "실패한_쿼리": failed}
    return result
