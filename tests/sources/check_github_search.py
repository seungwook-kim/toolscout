"""GitHub 검색 소스 검수 (2026-10-09). 고정 가짜 응답으로 확인한다. 네트워크를 쓰지 않는다.

실행: uv run python -m tests.sources.check_github_search
- 쿼리: 토픽 5개, 날짜 창(created:>=7일 전 날짜), 별 기준(MCP 10·스킬 30), 포크·보관 제외 조건, 별 수 정렬 1페이지 100개
- 포크·보관·설명 없음·창 밖·별 기준 미달 제외, 종류 판정(mcp-server > 스킬 토픽 > mcp), 한 저장소는 하나로
- 게시자당 3건, 종류마다 상위 20건, item url은 레지스트리와 같은 https://github.com/owner/repo
- 설치 정보: package.json(bin)+npm 실제 있음, pyproject([project.scripts])+PyPI 있음, 남의 패키지·없는 패키지·bin 없음은 비움
- 토큰 없으면 오류로 넘어감(검색 안 부름), 쿼리 일부 실패는 나머지로 진행, 전부 실패하면 오류
- 레지스트리와 같은 저장소가 겹치면 하나만 남고 레지스트리(설치 정보 있는 쪽)가 대표, 출처 등급 2
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

from pipeline.dedupe import SOURCE_TIER, dedupe
from pipeline.normalize import normalize
from sources import github_search

NOW = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("통과 " if ok else "실패 ") + name)


def repo(owner: str, name: str, stars: int, topics: list[str], *, desc: str | None = "설명", fork: bool = False, archived: bool = False,
         created: str = "2026-10-05T10:00:00Z") -> dict:
    return {"full_name": f"{owner}/{name}", "owner": {"login": owner}, "stargazers_count": stars, "topics": topics, "description": desc,
            "fork": fork, "archived": archived, "created_at": created, "default_branch": "main"}


class Resp:
    def __init__(self, body=None, status=200, text=None):
        self.body, self.status_code, self.text = body, status, text if text is not None else json.dumps(body or {})

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=httpx.Request("GET", "https://x"), response=httpx.Response(self.status_code))


PACKAGE_JSON = {"acme/npm-srv": {"name": "npm-srv", "bin": {"npm-srv": "cli.js"}},
                "acme/stolen": {"name": "stolen", "bin": "cli.js"},  # npm에 있지만 남의 저장소 소유
                "acme/ghost": {"name": "ghost", "bin": "cli.js"},  # npm에 없음
                "acme/nobin": {"name": "nobin"}}  # bin 없음
PYPROJECT = {"dev/py-srv": '[project]\nname = "py-srv"\n[project.scripts]\npy-srv = "py_srv:main"\n',
             "acme/pylib": '[project]\nname = "pylib"\n'}  # scripts 없음
NPM = {"npm-srv": {"name": "npm-srv", "version": "1.2.3", "repository": {"url": "git+https://github.com/Acme/npm-srv.git"}},
       "stolen": {"name": "stolen", "version": "9.9.9", "repository": {"url": "https://github.com/other/stolen"}},
       "nobin": {"name": "nobin", "version": "1.0.0", "repository": "https://github.com/acme/nobin"}}
PYPI = {"py-srv": {"info": {"name": "py-srv", "version": "0.4.0", "home_page": "", "project_urls": {"Source": "https://github.com/dev/py-srv"}}},
        "pylib": {"info": {"name": "pylib", "version": "1.0", "project_urls": {"Source": "https://github.com/acme/pylib"}}}}


class Client:
    def __init__(self, search: dict[str, list[dict]], fail: set[str] | None = None):
        self.search, self.fail, self.queries, self.urls = search, fail or set(), [], []
        self.other_headers = []

    def get(self, url, params=None, headers=None):
        self.urls.append(url)
        if url != github_search.URL:
            self.other_headers.append(headers)
        if url == github_search.URL:
            query = params["q"]
            self.queries.append((query, params, headers))
            topic = query.split()[0].removeprefix("topic:")
            if topic in self.fail:
                return Resp(status=500)
            return Resp({"items": self.search.get(topic, [])})
        if url.startswith("https://raw.githubusercontent.com/"):
            full = "/".join(url.split("/")[3:5])
            if url.endswith("/package.json") and full in PACKAGE_JSON:
                return Resp(text=json.dumps(PACKAGE_JSON[full]))
            if url.endswith("/pyproject.toml") and full in PYPROJECT:
                return Resp(text=PYPROJECT[full])
            return Resp(status=404, text="404")
        if url.startswith("https://registry.npmjs.org/"):
            data = NPM.get(url.split("/")[-2])
            return Resp(data) if data else Resp(status=404)
        if url.startswith("https://pypi.org/pypi/"):
            data = PYPI.get(url.split("/")[-2])
            return Resp(data) if data else Resp(status=404)
        raise AssertionError(url)


SEARCH = {
    "mcp-server": [repo("big", "srv1", 900, ["mcp", "mcp-server"]), repo("acme", "npm-srv", 80, ["mcp-server"]),
                   repo("acme", "stolen", 70, ["mcp-server"]), repo("acme", "ghost", 60, ["mcp-server"]),
                   repo("acme", "nobin", 50, ["mcp-server"]),  # acme 4번째 → 게시자당 3건 제한에 걸림
                   repo("forky", "f", 500, ["mcp-server"], fork=True), repo("old", "arch", 500, ["mcp-server"], archived=True),
                   repo("nodesc", "x", 500, ["mcp-server"], desc=None), repo("blank", "y", 500, ["mcp-server"], desc="  ")],
    "mcp": [repo("big", "srv1", 900, ["mcp", "mcp-server"]),  # 같은 저장소가 두 쿼리에 → 하나
            repo("dev", "py-srv", 40, ["mcp"]),
            repo("zed", "client", 30, ["mcp"]),
            repo("both", "skillish", 300, ["mcp", "claude-skills"]),  # 스킬 토픽이 더 구체적 → 스킬
            repo("early", "outside", 99, ["mcp-server"], created="2026-10-01T23:00:00Z"),  # 창(10/2 00:00) 밖
            repo("low", "tiny", 9, ["mcp"])],
    "claude-skills": [repo("sk", "s1", 500, ["claude-skills"]), repo("both", "skillish", 300, ["mcp", "claude-skills"]),
                      repo("sk", "s2", 400, ["claude-skills"]), repo("sk", "s3", 300, ["claude-skills"]), repo("sk", "s4", 200, ["claude-skills"])],
    "agent-skills": [repo("p", "mid", 35, ["agent-skills"]), repo("q", "low", 29, ["agent-skills"]),
                     repo("mixed", "m", 100, ["agent-skills", "mcp-server"])],  # mcp-server가 가장 앞 → MCP
    "claude-code-skills": [],
}

# ---- 쿼리
client = Client(SEARCH)
result = github_search.fetch(SINCE, client, token="fake-token")
queries = [q for q, _, _ in client.queries]
topics_of = lambda q: q.split()[0]  # noqa: E731
check("토픽 5개를 한 번씩만 부른다(검색 API 분당 30회 안)", sorted(topics_of(q) for q in queries) == sorted(
    f"topic:{t}" for t in ("mcp-server", "mcp", "claude-skills", "agent-skills", "claude-code-skills")))
check("날짜 창: created:>=7일 전 날짜, 포크·보관 제외 조건", all("created:>=2026-10-02" in q and "fork:false" in q and "archived:false" in q for q in queries))
is_mcp_query = lambda q: topics_of(q) in ("topic:mcp-server", "topic:mcp")  # noqa: E731
check("별 기준: MCP 토픽 10 이상·스킬 토픽 30 이상", all(("stars:>=10" in q) if is_mcp_query(q) else ("stars:>=30" in q) for q in queries))
check("별 수 내림차순 1페이지 100개, 토큰은 헤더로만", all(p["sort"] == "stars" and p["order"] == "desc" and p["per_page"] == 100
                                                  and h["Authorization"] == "Bearer fake-token" and "fake-token" not in q
                                                  for q, p, h in client.queries))
check("검색 말고 다른 곳(raw·npm·PyPI)에는 토큰 헤더를 보내지 않는다", client.other_headers and all(h is None for h in client.other_headers))

# ---- 제외·종류·상한
by_title = {i["title"]: i for i in result.items}
mcp = [i for i in result.items if i["type"] == "mcp"]
skill = [i for i in result.items if i["type"] == "skill"]
excluded = {"f (forky)", "arch (old)", "x (nodesc)", "y (blank)", "outside (early)", "tiny (low)", "low (q)"}
check("포크·보관·설명 없음(None·공백)·창 밖·별 기준 미달 제외", not excluded & set(by_title))
check("제외 건수를 stats에 남김", result.stats["제외"]["포크"] == 1 and result.stats["제외"]["보관"] == 1
      and result.stats["제외"]["설명없음"] == 2 and result.stats["제외"]["창_밖"] == 1 and result.stats["제외"]["별_기준_미달"] == 2)
check("같은 저장소가 여러 쿼리에 걸려도 하나", sum(1 for i in result.items if i["url"] == "https://github.com/big/srv1") == 1)
check("종류: mcp+claude-skills는 스킬, agent-skills+mcp-server는 MCP, mcp만이면 MCP",
      by_title["skillish (both)"]["type"] == "skill" and by_title["m (mixed)"]["type"] == "mcp" and by_title["client (zed)"]["type"] == "mcp")
check("스킬 별 기준 30: 35는 통과, 29는 제외", "mid (p)" in by_title and "low (q)" not in by_title)
check("게시자당 3건: acme MCP는 별 수 상위 3건", sorted(i["title"] for i in mcp if i["title"].endswith("(acme)")) == [
    "ghost (acme)", "npm-srv (acme)", "stolen (acme)"] and "nobin (acme)" not in by_title)
check("게시자당 3건: 스킬 sk는 s1·s2·s3", sorted(i["title"] for i in skill if i["title"].endswith("(sk)")) == ["s1 (sk)", "s2 (sk)", "s3 (sk)"])
check("별 수 순 정렬(항목 stars는 검색 응답 stargazers_count)", [i["stars"] for i in mcp] == sorted((i["stars"] for i in mcp), reverse=True)
      and by_title["srv1 (big)"]["stars"] == 900)
check("url 형식은 레지스트리와 같다", by_title["srv1 (big)"]["url"] == "https://github.com/big/srv1"
      and by_title["srv1 (big)"]["source"] == "github_search" and by_title["srv1 (big)"]["published_at"].startswith("2026-10-05"))
check("스킬은 skill_url(기본 브랜치)", by_title["s1 (sk)"]["skill_url"] == "https://github.com/sk/s1/tree/main")

# ---- 상위 N
many = {"mcp-server": [repo(f"o{n}", f"r{n}", 1000 - n, ["mcp-server"]) for n in range(30)],
        "claude-skills": [repo(f"s{n}", f"k{n}", 1000 - n, ["claude-skills"]) for n in range(30)]}
big = github_search.fetch(SINCE, Client(many), token="t")
check("종류마다 상위 20건", [sum(1 for i in big.items if i["type"] == k) for k in ("mcp", "skill")] == [20, 20]
      and any(i["title"] == "r19 (o19)" for i in big.items) and not any(i["title"] == "r20 (o20)" for i in big.items))

# ---- 설치 정보
inst = {i["title"]: i.get("install") for i in mcp}
check("npm: package.json(bin)+npm 실제 있고 저장소가 같으면 붙임(레지스트리 모양)", inst["npm-srv (acme)"] == {"packages": [
    {"registryType": "npm", "identifier": "npm-srv", "version": "1.2.3", "transport": "stdio"}]})
check("PyPI: [project.scripts]+PyPI 실제 있고 저장소가 같으면 붙임", inst["py-srv (dev)"] == {"packages": [
    {"registryType": "pypi", "identifier": "py-srv", "version": "0.4.0", "transport": "stdio"}]})
check("남의 저장소 패키지·npm에 없음은 비움(install 키 자체가 없음)", "install" not in by_title["stolen (acme)"] and "install" not in by_title["ghost (acme)"])
check("파일이 없는 저장소는 비움", "install" not in by_title["srv1 (big)"] and "install" not in by_title["client (zed)"])
check("설치 정보 붙은 수를 stats에 남김", result.stats["MCP_설치정보_붙음"] == 2 and result.stats["MCP_후보"] == len(mcp))
check("스킬에는 install을 붙이지 않고 설치 조회도 안 한다", all("install" not in i for i in skill)
      and not any("/sk/" in u or "/p/" in u for u in client.urls))

# ---- 토큰·실패
before = os.environ.pop("GITHUB_TOKEN", None)
try:
    c0 = Client(SEARCH)
    envless = github_search.fetch(SINCE, c0)
finally:
    if before is not None:
        os.environ["GITHUB_TOKEN"] = before
check("토큰이 없으면 오류로 기록하고 검색은 부르지 않는다", envless.error == "GITHUB_TOKEN 없음" and not envless.items and not c0.queries)
partial = github_search.fetch(SINCE, Client(SEARCH, fail={"mcp"}), token="t")
check("쿼리 하나가 실패해도 나머지로 진행(오류 아님, 실패 기록)", partial.error is None and partial.items and len(partial.stats["실패한_쿼리"]) == 1)
alldown = github_search.fetch(SINCE, Client(SEARCH, fail=set(SEARCH)), token="t")
check("전부 실패하면 오류", alldown.error.endswith("HTTP 500") and not alldown.items)

# ---- 레지스트리와 겹침
registry = {"title": "io.github.big/srv1 2.0.0", "url": "https://github.com/Big/srv1", "published_at": "2026-10-06T00:00:00+00:00",
            "summary": "레지스트리 설명", "source": "mcp_registry", "type": "mcp",
            "install": {"packages": [{"registryType": "npm", "identifier": "srv1", "version": "2.0.0", "transport": "stdio"}]}}
merged = dedupe(normalize([*result.items, registry]))
same = [i for i in merged if i["url"].lower() == "https://github.com/big/srv1"]
check("같은 저장소가 두 출처에서 오면 하나만 나간다", len(same) == 1)
check("남는 쪽은 레지스트리(설치 정보 있음), GitHub 검색은 also_reported_by에", same[0]["source"] == "mcp_registry" and same[0].get("install")
      and any(a["source"] == "github_search" for a in same[0]["also_reported_by"]))
check("겹치지 않는 GitHub 검색 항목은 그대로 남는다", any(i["source"] == "github_search" and i["title"] == "npm-srv (acme)" for i in merged))
check("출처 등급: GitHub 검색 2, 레지스트리 1", SOURCE_TIER.get("github_search") == 2 and SOURCE_TIER["mcp_registry"] == 1)

passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
