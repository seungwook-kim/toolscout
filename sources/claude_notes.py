"""Claude 공식 릴리스 노트 (2026-10-08 사용자 결정 "기억하고 수정하자"). Anthropic·Claude 발표(모델 출시, 요금·크레딧·한도)를 원문으로 받는다.

10/8 메일에서 "Max·Team 요금제 월 API 크레딧" 공지가 빠졌다. Anthropic 뉴스·Claude 블로그는 RSS가 없고(404), support.claude.com
릴리스 노트 한 쪽에 날짜(h3)마다 굵은 제목 문단 + 본문 문단으로 모인다(10/8 확인: "Claude Haiku 5.5 launch",
"Monthly API credits for Max and Team plans"). 이 쪽을 읽어 날짜 창 안 항목만 뉴스로 낸다.
- 링크: 본문의 첫 http(s) 링크(블로그·도움말 원문). 없으면 릴리스 노트 쪽 + 날짜 앵커
- 날짜: h3 날짜. 시각이 없어 그날 00:00 UTC로 둔다
- 공식 출처라 출처 등급 1 (pipeline/dedupe.SOURCE_TIER)
"""
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx

from sources.common import SourceResult, error_text, make_item

NAME = "claude_notes"
URL = "https://support.claude.com/en/articles/12138966-release-notes"
SUMMARY_LIMIT = 600


class _Blocks(HTMLParser):
    """글 본문을 [(kind, text, extra)]로 편다. kind: date(h3, extra=앵커 id) · title(굵은 글자만 있는 문단) · body(문단, extra=링크 목록)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str, object]] = []
        self._tag: str | None = None
        self._id = ""
        self._text: list[str] = []
        self._bold: list[str] = []
        self._links: list[str] = []
        self._depth_bold = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("h3", "p"):
            self._tag, self._id, self._text, self._bold, self._links = tag, attrs.get("id") or "", [], [], []
        elif self._tag == "p" and tag in ("b", "strong"):
            self._depth_bold += 1
        elif self._tag == "p" and tag == "a" and (attrs.get("href") or "").startswith(("http://", "https://")):
            self._links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag in ("b", "strong") and self._depth_bold:
            self._depth_bold -= 1
        if tag != self._tag:
            return
        text = " ".join("".join(self._text).split())
        if tag == "h3" and text:
            self.blocks.append(("date", text, self._id))
        elif tag == "p" and text:
            bold = " ".join("".join(self._bold).split())
            self.blocks.append(("title", text, None) if bold == text else ("body", text, list(self._links)))
        self._tag = None

    def handle_data(self, data):
        if self._tag:
            self._text.append(data)
            if self._depth_bold:
                self._bold.append(data)


def parse(page: str) -> list[dict]:
    """반환: [{title, summary, url, published}] (쪽 순서 그대로, 최근 것이 위)."""
    parser = _Blocks()
    parser.feed(page)
    entries, day, anchor = [], None, ""
    for kind, text, extra in parser.blocks:
        if kind == "date":
            try:
                day = datetime.strptime(text, "%B %d, %Y").replace(tzinfo=timezone.utc)
                anchor = extra
            except ValueError:
                day = None
        elif kind == "title" and day is not None:
            entries.append({"title": text, "summary": "", "url": f"{URL}#{anchor}" if anchor else URL, "published": day, "_linked": False})
        elif kind == "body" and entries and entries[-1]["published"] == day:
            entry = entries[-1]
            entry["summary"] = (entry["summary"] + " " + text).strip()[:SUMMARY_LIMIT]
            if extra and not entry["_linked"]:
                entry["url"], entry["_linked"] = extra[0], True
    for entry in entries:
        entry.pop("_linked")
    return entries


def fetch(since: datetime, client: httpx.Client) -> SourceResult:
    result = SourceResult(NAME)
    try:
        response = client.get(URL)
        response.raise_for_status()
    except Exception as exc:
        result.error = error_text(exc)
        return result
    entries = parse(response.text)
    result.fetched = len(entries)
    result.items = [make_item(title=f"Claude: {e['title']}", url=e["url"], published=e["published"], summary=e["summary"],
                              source=NAME, type="news") for e in entries if e["published"] >= since]
    return result
