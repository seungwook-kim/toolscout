"""뉴스 창 48시간과 큐레이터 제외 규칙 검수 (2026-09-21). 네트워크·모델을 쓰지 않는다.

왜: 하루 1회 07:00 실행에 창이 24시간이면 기사 하나가 후보에 오를 기회가 한 번뿐이다.
9월 17일 17시 36분에 나온 판단 전용 모델 Jev 공개 기사가 9월 18일 실행에서 밀린 뒤
창 밖으로 나가 9월 19일·20일 브리핑에 한 번도 오르지 못했다.

실행: uv run python -m tests.sources.check_news_window
- 창 48시간: 30시간 전 기사가 후보에 남고, 50시간 전 기사는 빠진다. 도구 창은 7일 그대로
- 다시 온 기회: 어제 밀린 기사가 오늘 실행에서 한 번 더 후보가 된다
- 중복 막기: 이미 보낸 항목은 seen_urls로 빠져 두 번 발송되지 않는다
- 제외 규칙: 자유 한 줄에 보기 싫다고 적은 기술은 큐레이터 프롬프트가 먼저 거른다
"""
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

from agent import curator
from agent.structured import Stats
from sources import collect, rss

NOW = datetime(2026, 9, 21, 7, 0, tzinfo=timezone.utc)
FEED = rss.Feed("aitimes", "https://example.test/rss")


def entry(title: str, hours_ago: int) -> str:
    when = (NOW - timedelta(hours=hours_ago)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (f"<item><title>{title}</title><link>https://example.test/{hours_ago}</link>"
            f"<pubDate>{when}</pubDate><description>검수 항목</description></item>")


class FakeResponse:
    def __init__(self, body: str):
        self.content = body.encode("utf-8")

    def raise_for_status(self) -> None:
        return None


class FakeClient:
    def __init__(self, body: str):
        self.body = body

    def get(self, url, **kwargs) -> FakeResponse:
        return FakeResponse(self.body)


def news_item(title: str, topic: str, url: str) -> dict:
    return {"title": title, "url": url, "type": "news", "source": "aitimes", "topic": topic,
            "summary": "검수 항목", "reason": "검수", "published_at": NOW.isoformat()}


def picks_everything():
    """받은 후보를 순서대로 고르는 가짜 큐레이터. 무엇이 후보로 들어왔는지만 본다."""
    seen: dict = {}

    def call(role, messages, tools=None):
        import re
        payload = json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S).group(1))
        seen["news"] = payload.get("news", [])
        picked = [{"id": n["id"], "why": "검수"} for n in payload.get("news", [])[:curator.schemas.MAX_NEWS]]
        return AIMessage(json.dumps({"news": picked, "tools": [], "empty_reason": None}))

    return call, seen


def main() -> int:
    body = ("<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>"
            + entry("30시간 전 기사", 30) + entry("50시간 전 기사", 50) + entry("2시간 전 기사", 2)
            + "</channel></rss>")
    since = NOW - collect.NEWS_WINDOW
    titles = {i["title"] for i in rss.fetch_feed(FEED, since, FakeClient(body)).items}

    # 어제 실행에 한 번 오르고 밀린 기사(30시간 전)가 오늘 실행 창에도 남는지.
    # 24시간 창이면 어제 창(어제 07:00 기준 48~24시간 전 자리)에만 들었다가 오늘은 빠져 기회가 한 번뿐이었다
    yesterday_run = NOW - timedelta(hours=24)
    missed_at = NOW - timedelta(hours=30)
    in_yesterday = yesterday_run - collect.NEWS_WINDOW <= missed_at < yesterday_run
    in_today_48 = since <= missed_at < NOW
    in_today_24 = NOW - timedelta(hours=24) <= missed_at < NOW
    second_chance = in_yesterday and in_today_48 and not in_today_24

    # 이미 보낸 항목은 seen_urls로 빠진다 (48시간 창에서 같은 기사가 다시 와도 두 번 가지 않는다)
    sent_url, fresh_url = "https://example.test/sent", "https://example.test/fresh"
    selected = [news_item("이미 보낸 기사", "model_release", sent_url),
                news_item("Jev 공개", "model_release", fresh_url)]
    memory_row = {"user_id": 1, "is_test": True, "seen_urls": [sent_url], "weights": {"model_release": 2},
                  "profile": {"role": "개발자", "tools_tags": [], "free_text": "Java·Spring 생태계 소식은 보고 싶지 않다"}}
    call, captured = picks_everything()
    plan = asyncio.run(curator.pick_for_user(selected, memory_row, Stats(), call))
    pool_titles = {n["title"] for n in captured.get("news", [])}

    checks = {
        "뉴스_창_48시간": collect.NEWS_WINDOW == timedelta(hours=48),
        "도구_창_7일_그대로": collect.TOOL_WINDOW == timedelta(days=7),
        "30시간_전_기사_후보에_남음": "30시간 전 기사" in titles,
        "50시간_전_기사_빠짐": "50시간 전 기사" not in titles,
        "최근_기사_그대로_남음": "2시간 전 기사" in titles,
        "어제_밀린_기사_오늘_다시_후보": second_chance,  # 24시간 창이면 오늘 빠졌을 기사다
        "이미_보낸_기사_후보에서_빠짐": "이미 보낸 기사" not in pool_titles,
        "안_보낸_기사_후보에_남음": "Jev 공개" in pool_titles,
        "이미_보낸_기사_두_번_안_감": all(card["url"] != sent_url for card in plan["news"]),
        "제외_규칙_프롬프트에_있음": "보기 싫다고 적힌" in curator.PICK_PROMPT and "먼저다" in curator.PICK_PROMPT,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
