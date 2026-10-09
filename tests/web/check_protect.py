"""보호 장치 검수 (2026-10-09, 1차). 모델 호출 없음, DB 없음.

실행: uv run python -m tests.web.check_protect
- 운영 모드(앱을 docs=False로 만듦)는 /docs·/redoc·/openapi.json 404, 개발 모드는 200
- /static 허용 목록: manifest.json·app.js·아이콘 200, README.md·CHANGELOG.md·demo_sample.json 404
- AI 크롤러 UA는 403(robots.txt·tdmrep.json은 200), 일반 브라우저·검수 클라이언트 UA는 200
- X-Robots-Tag(noai, noimageai 모든 응답, 데모·로그인 말고는 noindex, nofollow), TDM 헤더, tdmrep.json, robots.txt 이름별 차단
- web/*.js·*.css 첫 줄 고지, HTML head의 tdm-reservation meta와 고지 주석
"""
import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from routes import protect

ROOT = Path(__file__).resolve().parents[2]
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
NOTICE = "/*! © 2026 toolscout. All rights reserved. 무단 복제·재배포·AI 학습·재구현 금지 */"
CRAWLER_UAS = ["Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
               "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "CCBot/2.0 (https://commoncrawl.org/faq/)",
               "Mozilla/5.0 (compatible; PerplexityBot/1.0)", "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)"]


def tags(response) -> list[str]:
    return [v.strip() for v in response.headers.get("x-robots-tag", "").split(",")]


def main() -> int:
    import main as app_main

    prod = TestClient(app_main.make_app(docs=False), base_url="https://testserver", headers={"user-agent": BROWSER})
    dev = TestClient(app_main.make_app(docs=True), base_url="https://testserver", headers={"user-agent": BROWSER})
    robots = prod.get("/robots.txt")
    tdm = prod.get("/.well-known/tdmrep.json")
    crawler = [prod.get("/login", headers={"user-agent": ua}) for ua in CRAWLER_UAS]
    crawler_robots = prod.get("/robots.txt", headers={"user-agent": CRAWLER_UAS[0]})
    crawler_tdm = prod.get("/.well-known/tdmrep.json", headers={"user-agent": CRAWLER_UAS[1]})
    crawler_static = prod.get("/static/app.js", headers={"user-agent": CRAWLER_UAS[2]})
    crawler_api = prod.get("/api/health", headers={"user-agent": CRAWLER_UAS[3]})
    login, demo, home, health = prod.get("/login"), prod.get("/demo"), prod.get("/", follow_redirects=False), prod.get("/api/health")
    static_ok = {name: prod.get(f"/static/{name}").status_code for name in ("manifest.json", "app.js", "app.css", "icons/icon-192.png", "login.html")}
    static_no = {name: prod.get(f"/static/{name}").status_code for name in ("README.md", "CHANGELOG.md", "demo_sample.json", "../main.py", "%2e%2e/main.py")}
    web_files = sorted((ROOT / "web").glob("*.js")) + sorted((ROOT / "web").glob("*.css"))
    pages = sorted((ROOT / "web").glob("*.html"))
    names = [line.split(": ", 1)[1] for line in robots.text.splitlines() if line.startswith("User-agent: ")]
    checks = {
        "운영_docs_redoc_openapi_404": all(prod.get(p).status_code == 404 for p in ("/docs", "/redoc", "/openapi.json")),
        "개발_docs_redoc_openapi_200": all(dev.get(p).status_code == 200 for p in ("/docs", "/redoc", "/openapi.json")),
        "정적_허용_목록_200": all(code == 200 for code in static_ok.values()),
        "정적_허용_밖_404": all(code == 404 for code in static_no.values()),
        "AI_UA_403": all(r.status_code == 403 for r in crawler) and crawler_static.status_code == 403 and crawler_api.status_code == 403,
        "AI_UA도_robots·tdmrep는_200": crawler_robots.status_code == 200 and crawler_tdm.status_code == 200,
        "일반_UA_200": login.status_code == 200 and demo.status_code == 200 and health.status_code == 200 and home.status_code == 303,
        "검수_클라이언트_기본_UA_200": TestClient(app_main.make_app(docs=False), base_url="https://testserver").get("/login").status_code == 200,
        "robots_일반_규칙_유지": "User-agent: *\nAllow: /demo\nAllow: /privacy\nAllow: /terms\nAllow: /policy\nAllow: /support\nDisallow: /archive/full-index\nDisallow: /\n" in robots.text,
        "robots_AI_이름별_차단": all(n in names for n in ("GPTBot", "ClaudeBot", "Claude-User", "Google-Extended", "Applebot-Extended", "CCBot"))
        and len(names) == len(protect.AI_CRAWLERS) + 3 and all(n in names for n in protect.AI_CRAWLERS),
        "UA_검사_목록에_robots_전용_토큰_없음": not any(t in protect.AI_CRAWLERS for t in protect.ROBOTS_ONLY_TOKENS)
        and prod.get("/login", headers={"user-agent": "Google-Extended Applebot-Extended"}).status_code == 200,
        "모든_응답_noai": all({"noai", "noimageai"} <= set(tags(r)) for r in (login, demo, home, health, robots, tdm, crawler[0], prod.get("/static/app.js"), prod.get("/nope"))),
        "데모·로그인_말고는_noindex": all({"noindex", "nofollow"} <= set(tags(r)) for r in (home, health, robots, tdm, prod.get("/static/app.js"), prod.get("/signup"))),
        "데모는_색인_허용": "noindex" not in tags(demo) and "nofollow" not in tags(demo),
        "로그인_화면은_원래대로_noindex": "noindex" in tags(login),
        "TDM_헤더": all(r.headers.get("tdm-reservation") == "1" for r in (login, demo, health, crawler[0])),
        "tdmrep_json": tdm.status_code == 200 and tdm.json() == [{"location": "/*", "tdm-reservation": 1}],
        "JS·CSS_첫줄_고지": all(p.read_text(encoding="utf-8").splitlines()[0] == NOTICE for p in web_files) and len(web_files) >= 7,
        "HTML_head_tdm_meta·고지_주석": all('<meta name="tdm-reservation" content="1">' in p.read_text(encoding="utf-8")
                                         and "© 2026 toolscout. All rights reserved." in p.read_text(encoding="utf-8").split("</head>")[0] for p in pages) and len(pages) >= 10,
    }
    print(json.dumps({"checks": checks, "static_ok": static_ok, "static_no": static_no}, ensure_ascii=False, indent=2))
    ok = all(checks.values())
    print("통과" if ok else "실패")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
