"""수집 항목 정리: HTML 제거, 공백 정리, 추적 파라미터 제거 (계획안 9.2 W1 정규화).

입력과 출력 모양은 같다: {title, url, published_at, summary, source, type}.
"""
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}


def clean_text(value: str) -> str:
    return SPACE.sub(" ", html.unescape(TAG.sub(" ", value or ""))).strip()


def canonical_url(url: str) -> str:
    """같은 글을 같은 주소로 본다: 호스트 소문자, 조각(#) 제거, 추적 파라미터 제거, 끝 슬래시 제거."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def normalize(items: list[dict]) -> list[dict]:
    out = []
    for item in items:
        title = clean_text(item["title"])
        if not title or not item.get("url"):
            continue
        out.append({**item, "title": title, "url": canonical_url(item["url"]), "summary": clean_text(item.get("summary", ""))})
    return out
