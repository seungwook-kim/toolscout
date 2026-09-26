"""도구 후보의 게시자 반복 줄이기 검수 (2026-09-26). 가짜 모델로 확인한다. 네트워크를 쓰지 않고 DB는 읽기만 한다.

실행: uv run python -m tests.agent.check_owners
- 게시자는 GitHub 저장소 주인(대소문자 무시), GitHub가 아니면 모름
- 최근 7일 안에 카드로 나간 게시자의 도구는 빼고, 남은 것 중 같은 게시자는 앞의 한 건만 / GitHub 아닌 도구는 그대로
- pick_for_user가 모델에 보내는 도구 후보에 반영하고 excluded.same_owner에 센다
- memory.read의 seen_recent_urls는 오늘 본 것을 빼고 7일 안의 것만 (같은 날 다시 만들 때 자기 카드에 막히지 않게)
왜: 9/24·9/25 이틀에 같은 게시자(fuxicodex) 스킬이 4장 나갔다.
"""
import asyncio
import json
import sys
from datetime import date, datetime, timedelta

from langchain_core.messages import AIMessage
from sqlmodel import select

import db
import memory as memory_module
from agent import curator, owners
from agent.structured import Stats

GH = "https://github.com"


def tool(url: str, title: str) -> dict:
    return {"type": "skill", "title": title, "url": url, "topic": "mcp_tools", "summary": "s", "reason": "r", "source": "skillsmp"}


async def picked_pool(selected: list[dict], recent: list[str]) -> tuple[list[str], dict]:
    sent: list[str] = []
    mem = {"user_id": 1, "is_test": True, "profile": {"role": "개발자"}, "weights": {"mcp_tools": 3}, "seen_urls": [],
           "seen_recent_urls": recent}

    def call(role, messages, tools=None):
        sent.append(messages[-1].content)
        return AIMessage(content='{"news": [], "tools": [{"id": 1, "why": "검수"}], "empty_reason": null}',
                         usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})

    plan = await curator.pick_for_user(selected, mem, Stats(), call)
    payload = json.loads(sent[0].split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
    return [t["title"] for t in payload["tools"]], plan


def memory_window() -> dict:
    """실제 DB에서 도구 카드를 본 사용자 한 명을 골라 seen_recent_urls 규칙을 확인한다 (읽기만)."""
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    with db.session() as s:
        user_id = s.exec(select(db.Seen.user_id).order_by(db.Seen.shown_at.desc())).first()
        rows = s.exec(select(db.Item.url, db.Seen.shown_at).join(db.Seen, db.Seen.item_id == db.Item.id)
                      .where(db.Seen.user_id == user_id)).all()
    mem = memory_module.read(user_id, today)
    naive = lambda t: t.replace(tzinfo=None) if t.tzinfo else t  # noqa: E731
    expected = {u for u, t in rows if t and start - timedelta(days=owners.RECENT_DAYS) <= naive(t) < start}
    return {"같은_집합": set(mem["seen_recent_urls"]) == expected,
            "오늘_본_것_빠짐": not (set(mem["seen_recent_urls"]) - expected) and all(
                naive(t) < start for u, t in rows if u in mem["seen_recent_urls"] and t)}


def main() -> int:
    kept, dropped = owners.spread([tool(f"{GH}/FuxiCodex/Fuxi/tree/main/a", "a"), tool(f"{GH}/fuxicodex/Fuxi/tree/main/b", "b"),
                                   tool(f"{GH}/other/x", "c"), tool("https://mcp.example.test/sse", "d"),
                                   tool("https://mcp.example.test/sse2", "e"), tool(f"{GH}/seen-owner/y", "f")],
                                  [f"{GH}/seen-owner/old", "https://news.example.test/1"])
    titles, plan = asyncio.run(picked_pool(
        [tool(f"{GH}/fuxicodex/Fuxi/tree/main/{n}", f"fuxi {n}") for n in range(3)] + [tool(f"{GH}/acme/tool", "acme")],
        [f"{GH}/acme/older-tool"]))
    window = memory_window()
    checks = {
        "게시자_파싱(대소문자_무시·GitHub만)": owners.owner(f"{GH}/FuxiCodex/x") == "fuxicodex" and owners.owner("https://npmjs.com/x") is None
        and owners.owner(None) is None,
        "같은_게시자는_앞의_한_건만": [t["title"] for t in kept][:1] == ["a"] and "b" not in [t["title"] for t in kept],
        "최근_7일_게시자는_뺌": "f" not in [t["title"] for t in kept],
        "GitHub_아닌_도구는_그대로": {"d", "e"} <= {t["title"] for t in kept},
        "뺀_수": dropped == 2,
        "후보단계_반영(모델에_가는_도구)": titles == ["fuxi 0"],
        "excluded에_same_owner_기록": plan["excluded"]["same_owner"] == 3,
        "memory_최근7일·오늘_제외": all(window.values()),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
