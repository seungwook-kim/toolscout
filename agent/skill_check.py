"""read_skill 구현 (계획안 5장 도구 가드, 부록 D 스킬 흐름, 세션 8). SKILL.md 원문 가져오기 + 위험 신호 정규식.

- 원문은 GitHub(github.com tree·blob, raw.githubusercontent.com)와 SkillsMP(skillsmp.com → API로 GitHub 주소)만. 리다이렉트는 따라가지 않는다
- 모델에 넘기는 원문은 10,000자로 자르고 <data>로 감싼다. 정규식은 자르기 전 전체(최대 200KB)에 돌린다 (뒤에 숨긴 명령도 잡게)
- 정규식 5종: 외부 전송, 자격증명 요청, 권한 상승, 숨은 명령(base64·난독·보이지 않는 문자), 판독 지시("안전하다고 답하라" 류)
- 걸린 문장을 인용으로 돌려준다. 공식 출처(anthropics/skills)면 official=True (위험 신호 생략은 검증관이 판단에 반영)
이 결과는 위험 신호 분석이지 악성 여부나 안전을 확정하는 판정이 아니다.
"""
import os
import re
from urllib.parse import urlsplit

import httpx

TEXT_LIMIT, SCAN_LIMIT, QUOTE_CHARS = 10_000, 200_000, 200
SKILLSMP_SEARCH = "https://skillsmp.com/api/v1/skills/search"
INVISIBLE = re.compile("[\u200b-\u200f\u2060\ufeff]")
OFFICIAL = re.compile(r"^(https://github\.com/anthropics/skills/|https://raw\.githubusercontent\.com/anthropics/skills/)")

PATTERNS: dict[str, list[re.Pattern]] = {
    "외부 전송": [
        re.compile(r"\b(curl|wget|Invoke-WebRequest|iwr|requests\.(post|put)|httpx\.(post|put)|axios\.(post|put)|fetch\()"
                   r"[^\n]{0,120}https?://", re.I),
        re.compile(r"\b(send|upload|post|transmit|forward|exfiltrat\w*|report)\w*\b[^\n.]{0,80}\b(to|into)\b[^\n.]{0,40}https?://", re.I),
        re.compile(r"(전송|업로드|보내)[^\n.]{0,40}https?://|https?://\S+[^\n]{0,40}(으로|로|에)\s*(전송|업로드|보내|보고)"),
        re.compile(r"discord(app)?\.com/api/webhooks|hooks\.slack\.com/services|webhook\.site|requestbin|ngrok\.io|pastebin\.com", re.I),
    ],
    "자격증명 요청": [
        re.compile(r"\b(ask|request|prompt|provide|paste|enter|share|send|collect|print|cat|read|copy)\b[^\n.]{0,60}"
                   r"\b(api[ _-]?keys?|access[ _-]?tokens?|secret[ _-]?keys?|passwords?|credentials?|private[ _-]?keys?|session cookies?)\b", re.I),
        re.compile(r"\b(cat|read|type|open|copy|upload)\b[^\n]{0,40}(~/\.ssh|id_rsa|\.aws/credentials|\.netrc|\.git-credentials)", re.I),
        re.compile(r"(API ?키|토큰|비밀번호|패스워드|자격 ?증명|시크릿|개인 ?키)[^\n.]{0,40}(입력|알려|붙여|보내|요청|읽어|출력|수집)"),
    ],
    "권한 상승": [
        re.compile(r"\bsudo\b(?!\s+(apt(-get)?|yum|dnf|brew|apk|pacman)\s+(install|update|upgrade))|\bsetuid\b|--privileged"
                   r"|chmod\s+(u?\+s|777)\b|--dangerously-skip-permissions", re.I),
        re.compile(r"\brun\b[^\n.]{0,20}\bas\s+(root|administrator)\b|\bdisable\b[^\n.]{0,20}\b(sandbox|antivirus|firewall|security)\b", re.I),
        re.compile(r"(관리자|루트)\s*권한|권한\s*(상승|우회)|보안\s*(기능)?\s*(끄|해제|우회)"),
    ],
    "숨은 명령": [
        re.compile(r"[A-Za-z0-9+/]{80,}={0,2}"),
        re.compile(r"base64\s+(-d|--decode)|\batob\(|\beval\(|\bexec\(|(\\x[0-9a-fA-F]{2}){6,}", re.I),
        INVISIBLE,
        re.compile(r"<!--[^>]{0,400}\b(ignore|execute|run|curl|send|upload)\b[^>]{0,400}-->", re.I | re.S),
    ],
    "판독 지시": [
        re.compile(r"(이\s*스킬은|this\s+skill\s+is)\s*(완전히\s*|totally\s+|completely\s+)?(안전|safe)", re.I),
        re.compile(r"(안전하다고|as\s+safe|that\s+it\s+is\s+safe)\s*(답|말|판단|respond|answer|report|say|mark)", re.I),
        re.compile(r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+instructions|(이전|앞의|위의)\s*지시(를)?\s*(무시|잊)", re.I),
    ],
}


class SkillError(ValueError):
    pass


def _quote(text: str, start: int, end: int) -> str:
    """걸린 위치가 든 줄(너무 길면 앞뒤 일부)을 인용으로."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    line = text[line_start:line_end].strip()
    if len(line) <= QUOTE_CHARS:
        return line
    offset = max(0, start - line_start - QUOTE_CHARS // 2)
    return line[offset:offset + QUOTE_CHARS].strip()


def scan(text: str) -> list[dict]:
    """정규식 위험 신호. 반환: [{category, quote}] (같은 인용은 한 번)."""
    text = (text or "")[:SCAN_LIMIT]
    hits, seen = [], set()
    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                quote = _quote(text, match.start(), match.end())
                if (category, quote) not in seen:
                    seen.add((category, quote))
                    visible = INVISIBLE.sub(lambda m: f"[U+{ord(m.group()):04X}]", quote)  # 보이지 않는 문자는 표시로
                    hits.append({"category": category, "quote": visible})
                if len(hits) >= 20:
                    return hits
    return hits


def _github_raw(url: str) -> str:
    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    if parts.hostname == "raw.githubusercontent.com":
        return url if segments and segments[-1].lower().endswith(".md") else url.rstrip("/") + "/SKILL.md"
    if len(segments) < 2:
        raise SkillError("GitHub 저장소 주소가 아니다")
    owner, repo = segments[0], segments[1]
    if len(segments) >= 4 and segments[2] in ("tree", "blob"):
        branch, path = segments[3], "/".join(segments[4:])
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}".rstrip("/")
        return raw if raw.lower().endswith(".md") else raw + "/SKILL.md"
    return f"https://raw.githubusercontent.com/{owner}/{repo}/main/SKILL.md"


def resolve(url: str, client: httpx.Client) -> tuple[str, str]:
    """반환: (원문 raw 주소, 사람이 볼 출처 주소). 허용 밖이면 SkillError."""
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        raise SkillError("https 주소만 받는다")
    if host in ("github.com", "raw.githubusercontent.com"):
        return _github_raw(url), url
    if host in ("skillsmp.com", "www.skillsmp.com"):
        slug = [s for s in parts.path.split("/") if s][-1] if parts.path.strip("/") else ""
        name = re.sub(r"^skills-", "", slug)
        headers = {"Authorization": f"Bearer {os.environ.get('SKILLSMP_API_KEY', '')}"}
        response = client.get(SKILLSMP_SEARCH, params={"q": name, "limit": 50}, headers=headers)
        response.raise_for_status()
        skills = response.json().get("data", {}).get("skills", [])
        match = next((s for s in skills if (s.get("skillUrl") or "").rstrip("/") == url.rstrip("/")), None)
        if not match or not match.get("githubUrl"):
            raise SkillError("SkillsMP에서 GitHub 원문 주소를 찾지 못함")
        return _github_raw(match["githubUrl"]), match["githubUrl"]
    raise SkillError("GitHub·SkillsMP 원문만 읽는다")


def wrap_data(url: str, text: str) -> str:
    return f'<data source="{url}">\n{text.replace("</data>", "&lt;/data&gt;")}\n</data>'


def read(url: str, client: httpx.Client | None = None) -> dict:
    """반환: {status: ok|rejected|error, url, raw_url, official, text(<data>), chars, truncated, hits[], regex_signal, reason?}."""
    own = client is None
    client = client or httpx.Client(timeout=20, follow_redirects=False, headers={"User-Agent": "toolscout/0.1 (skill review)"})
    try:
        try:
            raw_url, source = resolve(url, client)
        except SkillError as exc:
            return {"status": "rejected", "url": url, "reason": str(exc)}
        response = client.get(raw_url)
        if response.status_code != 200:
            return {"status": "error", "url": url, "raw_url": raw_url, "reason": f"원문 접근 불가(HTTP {response.status_code})"}
        full = response.text[:SCAN_LIMIT]
        hits = scan(full)
        return {"status": "ok", "url": source, "raw_url": raw_url, "official": bool(OFFICIAL.match(source) or OFFICIAL.match(raw_url)),
                "text": wrap_data(source, full[:TEXT_LIMIT]), "chars": len(full), "truncated": len(full) > TEXT_LIMIT,
                "hits": hits, "regex_signal": "caution" if hits else "ok"}
    except httpx.HTTPError as exc:
        return {"status": "error", "url": url, "reason": f"원문 접근 불가({type(exc).__name__})"}
    finally:
        if own:
            client.close()
