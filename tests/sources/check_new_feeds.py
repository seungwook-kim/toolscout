"""2026-10-16 추가한 원문·빠른 출처 8곳 검수 (사용자 "일반 AI보다 더 정확하고 빠른 뉴스").

실행: uv run python -m tests.sources.check_new_feeds [--live]
- 모든 RSS 소스에 출처 등급이 있고, 새 8곳은 회사 원문 1 · AI 전용 매체 2 · 개인 블로그 3
- 새 8곳의 기사 주소를 해설가 fetch_article이 읽을 수 있다(mcp_server.ALLOWED_DOMAINS). 빠지면 카드가 모두 "원문 확인 필요"가 된다
- --live: 새 8곳을 실제로 받아 오류 없이 48시간 창 안 항목이 나오는지 (네트워크, 모델은 부르지 않는다)
"""
import json
import sys
from datetime import datetime, timezone

import mcp_server
from pipeline.dedupe import SOURCE_TIER
from sources import rss
from sources.collect import NEWS_WINDOW
from sources.common import http_client

SAMPLE_URLS = ["https://deepmind.google/blog/x/", "https://mistral.ai/news/x", "https://developer.nvidia.com/blog/x/",
               "https://huggingface.co/blog/x", "https://github.blog/changelog/x/", "https://the-decoder.com/x/",
               "https://www.theverge.com/ai-artificial-intelligence/1/x", "https://simonwillison.net/2026/Oct/16/x/"]
NEW = {"deepmind": 1, "mistral": 1, "nvidia_dev": 1, "huggingface": 1, "github_changelog": 1,
       "the_decoder": 2, "verge_ai": 2, "simonwillison": 3}


def main() -> int:
    names = [f.name for f in rss.FEEDS]
    checks = {
        "모든_RSS_소스에_출처_등급": all(name in SOURCE_TIER for name in names),
        "새_8곳이_FEEDS에": set(NEW) <= set(names) and len(names) == len(set(names)),
        "새_8곳_출처_등급": all(SOURCE_TIER[name] == tier for name, tier in NEW.items()),
        "새_8곳_원문_도메인을_해설가가_읽을_수_있음": all(mcp_server.is_allowed(url) for url in SAMPLE_URLS),
    }
    live = {}
    if "--live" in sys.argv:
        now = datetime.now(timezone.utc)
        with http_client() as client:
            for feed in rss.FEEDS:
                if feed.name in NEW:
                    result = rss.fetch_feed(feed, now - NEWS_WINDOW, client)
                    live[feed.name] = {"error": result.error, "fetched": result.fetched, "in_window": len(result.items)}
        checks["새_8곳_모두_받아짐"] = all(not v["error"] and v["fetched"] > 0 for v in live.values())
        checks["48시간_창_안_항목이_있음"] = sum(v["in_window"] for v in live.values()) > 0
    for name, ok in checks.items():
        print(("통과 " if ok else "실패 ") + name)
    print(json.dumps({"pass": all(checks.values()), "live": live}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
