"""SkillsMP 스킬 수집 검수 (2026-09-23). 네트워크를 쓰지 않는다.

왜: 스킬 소스가 anthropics/skills 커밋 하나뿐이라 최근 10일 수집이 1건이었고 스킬 카드가 한 장도 나가지 않았다.
SkillsMP는 검색만 열려 있어 주제어로 나눠 훑고, updatedAt이 실제 갱신 시각이 아니라 긁어 간 시각이라
창 대신 "아직 안 본 주소"로 신규를 가린다.

실행: uv run python -m tests.sources.check_skillsmp
- 키가 없으면 건너뛴다 (오류 아님)
- 주제어마다 부르고 githubUrl로 합친다, 이미 items에 있는 주소는 뺀다
- 게시자당 3건, 별 수 상위 20건까지
- 항목에 type=skill·source=skillsmp·skill_url·stars, 주제어 하나가 실패해도 나머지로 진행
"""
import json
import os
import sys

from sources import skillsmp


def skill(name: str, author: str, stars: int, url: str | None = None) -> dict:
    return {"id": f"{author}-{name}", "name": name, "author": author, "stars": stars, "description": f"{name} 설명",
            "githubUrl": url or f"https://github.com/{author}/{name}", "updatedAt": 1779015027}


class FakeResponse:
    def __init__(self, skills: list[dict], status: int = 200):
        self._skills, self.status_code = skills, status

    def raise_for_status(self) -> None:
        if self.status_code != 200:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return {"data": {"skills": self._skills}}


class FakeClient:
    """주제어마다 다른 결과를 주고, 겹치는 스킬도 섞는다. fail에 든 주제어는 오류."""

    def __init__(self, fail: set[str] | None = None):
        self.fail, self.calls = fail or set(), []

    def get(self, url, params=None, headers=None) -> FakeResponse:
        query = (params or {}).get("q", "")
        self.calls.append(query)
        if query in self.fail:
            return FakeResponse([], status=500)
        common = [skill("shared", "acme", 100)]
        if query == "mcp":
            return FakeResponse(common + [skill(f"a{n}", "bigcorp", 900 - n) for n in range(5)])
        if query == "agent":
            return FakeResponse(common + [skill("old", "seen-author", 5000, url="https://github.com/seen/one")])
        return FakeResponse(common + [skill(f"{query}-tool", f"pub-{query}", 50)])


def run(monkey_known: set[str], fail: set[str] | None = None, key: str = "test-key"):
    before_key = os.environ.get("SKILLSMP_API_KEY")
    before_known = skillsmp.known_urls
    os.environ["SKILLSMP_API_KEY"] = key
    skillsmp.known_urls = lambda urls: {u for u in urls if u in monkey_known}
    try:
        client = FakeClient(fail)
        return skillsmp.fetch(client), client
    finally:
        skillsmp.known_urls = before_known
        if before_key is None:
            os.environ.pop("SKILLSMP_API_KEY", None)
        else:
            os.environ["SKILLSMP_API_KEY"] = before_key


def main() -> int:
    result, client = run(monkey_known={"https://github.com/seen/one"})
    urls = [i["url"] for i in result.items]
    authors = [i["title"].split("(")[-1].rstrip(")") for i in result.items]
    no_key, _ = run(monkey_known=set(), key="")
    partial, _ = run(monkey_known=set(), fail={"mcp"})
    all_failed, _ = run(monkey_known=set(), fail=set(skillsmp.QUERIES))

    checks = {
        "주제어마다_부름": client.calls == list(skillsmp.QUERIES),
        "같은_스킬은_한_번만": urls.count("https://github.com/acme/shared") == 1,
        "이미_본_주소는_제외": "https://github.com/seen/one" not in urls,
        "게시자당_3건_상한": max(authors.count(a) for a in set(authors)) <= skillsmp.MAX_PER_PUBLISHER,
        "별수_높은_것이_먼저": (result.items[0].get("stars") or 0) >= (result.items[-1].get("stars") or 0),
        "항목_규격": all(i["type"] == "skill" and i["source"] == "skillsmp" and i["skill_url"] == i["url"]
                       and "stars" in i for i in result.items),
        "상한_20건": len(result.items) <= skillsmp.MAX_NEW,
        "키_없으면_건너뜀": no_key.items == [] and no_key.error is None and "건너뜀" in no_key.stats,
        "주제어_하나_실패해도_진행": partial.error is None and partial.items and "mcp" in str(partial.stats["실패한_주제어"]),
        "전부_실패면_오류": all_failed.error is not None and all_failed.items == [],
        "통계_기록": {"주제어", "받은_서로_다른_스킬", "올린_것"} <= set(result.stats),
    }
    report = {"checks": checks, "올린_것": len(result.items), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
