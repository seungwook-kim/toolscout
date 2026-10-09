"""무단 복제·AI 크롤링을 어렵게 하는 1차 보호 장치 (2026-10-09).

- AI 크롤러 이름이 User-Agent에 들어 있으면 /robots.txt와 tdmrep.json 말고는 403
- 모든 응답에 X-Robots-Tag(noai, noimageai)와 TDM-Reservation: 1. 데모·로그인 말고는 noindex, nofollow도
- /static은 허용 목록(.html .js .css .png .svg .ico .webmanifest, manifest.json)만 내보낸다. 나머지는 404
- 함정 링크를 부른 클라이언트는 24시간 동안 robots.txt 말고 403 (2차, routes/guard.py). 유효한 로그인 세션 쿠키가 있으면 막지 않는다
- 못 막는 것: User-Agent를 속이는 크롤러, 브라우저로 화면을 직접 받아 가는 사람. 이 장치는 예의 바른 크롤러와 게으른 복제를 막는 정도다
"""
from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from routes import guard

# User-Agent에 들어 있으면 막는 AI 크롤러 이름(소문자 비교).
# Google-Extended·Applebot-Extended는 robots.txt 전용 토큰이라 UA에 오지 않으므로 여기엔 없다
AI_CRAWLERS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
    "CCBot", "PerplexityBot", "Perplexity-User", "Bytespider", "Amazonbot", "meta-externalagent", "meta-externalfetcher",
    "FacebookBot", "cohere-ai", "cohere-training-data-crawler", "Diffbot", "YouBot", "Omgilibot", "omgili",
    "ImagesiftBot", "Timpibot", "AI2Bot", "DuckAssistBot", "MistralAI-User", "PanguBot",
]
# robots.txt에만 쓰는 토큰(UA 검사에서는 뺀다)
ROBOTS_ONLY_TOKENS = ["Google-Extended", "Applebot-Extended"]

_BLOCKED = tuple(name.lower() for name in AI_CRAWLERS)
# 크롤러여도 읽게 두는 경로(규칙을 읽고 따를 수 있어야 한다)
READABLE = ("/robots.txt", "/.well-known/tdmrep.json")
# 검색 색인을 열어 두는 화면
INDEXABLE = ("/demo", "/login", "/privacy", "/terms")
STATIC_SUFFIXES = {".html", ".js", ".css", ".png", ".svg", ".ico", ".webmanifest"}
STATIC_NAMES = {"manifest.json"}


def robots_txt(general: str) -> str:
    """일반 규칙 위에 AI 크롤러를 이름으로 막는 규칙을 얹는다."""
    names = AI_CRAWLERS + ROBOTS_ONLY_TOKENS
    agents = "".join(f"User-agent: {name}\n" for name in names)
    return agents + "Disallow: /\n\n" + general


def is_ai_crawler(user_agent: str) -> bool:
    ua = user_agent.lower()
    return any(name in ua for name in _BLOCKED)


def robots_header(path: str, existing: str | None) -> str:
    """응답에 붙일 X-Robots-Tag. 화면이 이미 정한 값(noindex)은 지우지 않고 noai를 보탠다."""
    values = [v.strip() for v in existing.split(",")] if existing else []
    if path not in INDEXABLE and not path.startswith("/demo/"):
        values += ["noindex", "nofollow"]
    values += ["noai", "noimageai"]
    return ", ".join(dict.fromkeys(values))


class ProtectMiddleware:
    """순수 ASGI 미들웨어(/mcp 스트리밍을 건드리지 않으려고 BaseHTTPMiddleware를 쓰지 않는다)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        agent = next((v.decode("latin-1") for k, v in scope["headers"] if k == b"user-agent"), "")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = next((v.decode("latin-1") for k, v in headers if k.lower() == b"x-robots-tag"), None)
                headers = [(k, v) for k, v in headers if k.lower() != b"x-robots-tag"]
                headers.append((b"x-robots-tag", robots_header(path, existing).encode("latin-1")))
                headers.append((b"tdm-reservation", b"1"))
                message = {**message, "headers": headers}
            await send(message)

        async def deny(text: bytes) -> None:
            await send_with_headers({"type": "http.response.start", "status": 403,
                                     "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                                 (b"content-length", str(len(text)).encode())]})
            await send_with_headers({"type": "http.response.body", "body": text})

        if path not in READABLE and is_ai_crawler(agent):
            await deny(b"AI crawlers are not allowed.")
            return
        if path not in READABLE:
            headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
            if guard.session_uid(headers.get("cookie")) is None:  # 로그인 세션이 있으면 차단 대상이 아니다
                client = guard.client_of(headers, (scope.get("client") or ("?",))[0])
                if await run_in_threadpool(guard.is_blocked, client):
                    await deny(guard.BLOCK_MESSAGE.encode())
                    return
        await self.app(scope, receive, send_with_headers)


class AllowedStaticFiles(StaticFiles):
    """허용 목록 밖 파일(.md, demo_sample.json 등)은 있어도 404."""

    async def get_response(self, path: str, scope):
        name = path.rsplit("/", 1)[-1]
        suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if suffix not in STATIC_SUFFIXES and name not in STATIC_NAMES:
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)
