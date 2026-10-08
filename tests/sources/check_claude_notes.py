"""Claude 공식 릴리스 노트 소스 검수 (2026-10-08). 고정 HTML 조각으로 확인한다. 네트워크를 쓰지 않는다.

실행: uv run python -m tests.sources.check_claude_notes
- 날짜(h3)마다 굵은 제목 문단이 항목 하나, 뒤 문단이 요약, 요약의 첫 링크가 원문 링크(없으면 쪽 주소 + 날짜 앵커)
- 날짜 창 밖 항목은 빠지고, 제목 앞에 "Claude: ", 출처 이름 claude_notes·뉴스, 출처 등급 1(공식)
- 10/8 메일에서 빠졌던 "Monthly API credits for Max and Team plans"가 원문 링크와 함께 나온다
"""
import json
import sys
from datetime import datetime, timezone

from pipeline.dedupe import SOURCE_TIER
from sources import claude_notes

PAGE = """<article class="DocsArticleBody_body">
<h2 id="h_a">October 2026</h2>
<h3 id="h_oct7">October 7, 2026</h3>
<div><p><b>Claude Haiku 5.5 launch</b></p></div>
<div><p>We just launched Claude Haiku 5.5. See <b><a href="https://www.anthropic.com/claude-haiku-5-5">Claude Haiku 5.5</a></b>.</p></div>
<div><p> </p></div>
<div><p><b>Monthly API credits for Max and Team plans</b></p></div>
<div><p>Max and Team plans now include monthly API credits. Claim them in <b>Settings &gt; Billing</b>.
Learn more about <b><a href="https://support.claude.com/en/articles/17154008">monthly API credits</a></b>.</p></div>
<h2 id="h_b">September 2026</h2>
<h3 id="h_sep28">September 28, 2026</h3>
<div><p><b>Old feature without link</b></p></div>
<div><p>Something older.</p></div>
</article>"""

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, ok))
    print(("통과 " if ok else "실패 ") + name)


class Resp:
    status_code, text = 200, PAGE

    def raise_for_status(self):
        return None


class Client:
    def get(self, url):
        self.url = url
        return Resp()


entries = claude_notes.parse(PAGE)
check("날짜마다 굵은 제목이 항목 하나", [e["title"] for e in entries] == ["Claude Haiku 5.5 launch", "Monthly API credits for Max and Team plans",
                                                              "Old feature without link"])
check("요약은 뒤 문단, 첫 링크가 원문 링크", entries[1]["url"] == "https://support.claude.com/en/articles/17154008"
      and "monthly API credits" in entries[1]["summary"] and entries[0]["url"] == "https://www.anthropic.com/claude-haiku-5-5")
check("링크 없으면 쪽 주소 + 날짜 앵커", entries[2]["url"] == f"{claude_notes.URL}#h_sep28")
check("날짜는 h3 날짜(UTC 0시)", entries[1]["published"] == datetime(2026, 10, 7, tzinfo=timezone.utc))
client = Client()
result = claude_notes.fetch(datetime(2026, 10, 6, tzinfo=timezone.utc), client)
check("창 밖 항목은 빠지고 제목 앞 Claude:·출처·뉴스", result.fetched == 3 and [i["title"] for i in result.items] == [
    "Claude: Claude Haiku 5.5 launch", "Claude: Monthly API credits for Max and Team plans"]
      and all(i["source"] == "claude_notes" and i["type"] == "news" for i in result.items) and client.url == claude_notes.URL)
check("출처 등급 1(공식)", SOURCE_TIER.get("claude_notes") == 1)
passed = sum(ok for _, ok in results)
print(json.dumps({"pass": passed == len(results), "passed": passed, "total": len(results)}, ensure_ascii=False))
sys.exit(0 if passed == len(results) else 1)
