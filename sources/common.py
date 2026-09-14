"""소스 파서 공통: 정규화 항목 모양, HTTP 클라이언트, 날짜 해석."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import TypedDict

import httpx

import config  # noqa: F401  .env를 os.environ에 채운다 (GITHUB_TOKEN 등)

USER_AGENT ="toolscout/0.1 (personal AI briefing agent; +https://github.com/seungwook-kim/toolscout)"
KST = timezone(timedelta(hours=9))


class Item(TypedDict):
    """정규화 출력 (착수 프롬프트 8번)."""

    title: str
    url: str
    published_at: str  # UTC ISO 8601
    summary: str
    source: str
    type: str  # news, mcp, skill


@dataclass
class SourceResult:
    source: str
    items: list[Item] = field(default_factory=list)
    fetched: int = 0  # 창(24시간·7일) 적용 전 받은 건수
    error: str | None = None
    stats: dict = field(default_factory=dict)  # 필터 단계별 건수 (리포트용)


def http_client() -> httpx.Client:
    # 레딧은 User-Agent가 없으면 막는다. 모든 소스에 같은 정직한 UA를 보낸다.
    return httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def parse_date(value: str | None, naive_tz: timezone = timezone.utc) -> datetime | None:
    """RFC 822, ISO 8601 날짜를 UTC로 바꾼다. 시간대가 없으면 naive_tz로 본다."""
    if not value:
        return None
    text = value.strip()
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=naive_tz)
    return parsed.astimezone(timezone.utc)


def make_item(*, title: str, url: str, published: datetime, summary: str, source: str, type: str) -> Item:
    return Item(title=title.strip(), url=url.strip(), published_at=published.isoformat(timespec="seconds"),
                summary=(summary or "").strip(), source=source, type=type)


def error_text(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {str(exc)[:120]}"
