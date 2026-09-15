"""웹앱 본체 규칙 검수 (7단계). 모델 호출 없음.

실행: uv run python -m tests.web.check_rules
- 모든 /api/ 경로는 세션이 없으면 401 (예외: 상태 확인, 로그인 요청, 로그아웃, 메일 피드백 서명 링크, 서비스 키 API)
- 남의 데이터 접근 거부: 남의 항목 피드백, 남의 피드백 메모, 남의 날짜 브리핑은 빈 결과
- 화면 파일: 뷰포트 메타, app.css가 docs/design-reference.html의 style 그대로(640px 이하 한 줄), 긴 줄표 없음, 외부 스크립트 없음
- 이번 단계 제외 확인: SSE(text/event-stream) 없음, 공개 MCP 도구(get_briefing·ask_briefing) 없음
"""
import asyncio
import json
import re
import sys
from datetime import date
from pathlib import Path

from tests.web import common

from sqlalchemy import delete, insert  # noqa: E402

import db  # noqa: E402
from mcp_server import mcp  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
A, B = "web-rules-a@toolscout.test", "web-rules-b@toolscout.test"
HOST = "https://example.test/web-rules/"
DAY = date(2000, 1, 9)
# 세션 없이 열리는 API와 그 이유
OPEN = {
    "/api/health": "상태 확인",
    "/api/auth/request": "로그인 링크 요청",
    "/api/auth/logout": "쿠키 지우기",
    "/api/feedback/link": "메일 버튼 서명 링크(24시간·1회용)",
    "/api/feedback/link/note": "메일 링크 이상함 사유(1시간 서명)",
}
SERVICE_KEY = ("/api/w1/",)  # X-Service-Key


def api_routes(app) -> list[tuple[str, str]]:
    """앱에 직접 붙은 경로 + main.py가 포함한 라우터 모듈의 경로 (FastAPI가 포함 라우터를 감싸 두어 app.routes에 안 보인다)."""
    from fastapi.routing import APIRoute

    source = (ROOT / "main.py").read_text(encoding="utf-8")
    modules = re.search(r"from routes import ([\w, ]+)", source).group(1).replace(" ", "").split(",")
    found = [(m, r.path) for r in app.router.routes if isinstance(r, APIRoute) for m in r.methods]
    for name in modules:
        module = __import__(f"routes.{name}", fromlist=["router"])
        found += [(m, r.path) for r in module.router.routes if isinstance(r, APIRoute) for m in r.methods]
    return sorted({(m, path) for m, path in found if path.startswith("/api/") and m not in ("HEAD", "OPTIONS")})


def cleanup() -> None:
    common.cleanup_users("web-rules-")
    with db.get_engine().begin() as c:
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def main() -> int:
    import main as app_main

    cleanup()
    routes = api_routes(app_main.app)
    unguarded, statuses = [], {}
    try:
        cb = common.second_client()
        with common.client() as ca:
            for method, path in routes:
                url = re.sub(r"\{[^}]+\}", "1", path)
                response = ca.request(method, url, json={})
                statuses[f"{method} {path}"] = response.status_code
                if path in OPEN or path.startswith(SERVICE_KEY):
                    if path.startswith(SERVICE_KEY) and response.status_code not in (401, 403):
                        unguarded.append(f"{method} {path} {response.status_code}")
                elif response.status_code != 401:
                    unguarded.append(f"{method} {path} {response.status_code}")
            common.login(ca, A)
            common.login(cb, B)
            b_id = common.user_id(B)
            with db.get_engine().begin() as c:
                item_id = c.execute(insert(db.Item).values(date=DAY, type="news", topic="industry", title="규칙 검수", url=f"{HOST}1",
                                                           source="test").returning(db.Item.id)).scalar_one()
                c.execute(insert(db.Briefing).values(user_id=b_id, date=DAY, item_id=item_id, rank=1, trace_id="t",
                                                     card_json={"item_id": item_id, "type": "news", "title": "규칙 검수"}))
                b_feedback = c.execute(insert(db.Feedback).values(user_id=b_id, item_id=item_id, action="이상함", created_at=db.utcnow())
                                       .returning(db.Feedback.id)).scalar_one()
            other_item = ca.post("/api/feedback", json={"item_id": item_id, "action": "관심없음"})
            other_note = ca.post(f"/api/feedback/{b_feedback}/note", json={"reason": "사실 틀림"})
            other_day = ca.get(f"/api/briefings?date={DAY}").json()
            own_day = cb.get(f"/api/briefings?date={DAY}").json()
    finally:
        cleanup()
    pages = sorted((ROOT / "web").glob("*.html"))
    web_files = pages + sorted((ROOT / "web").glob("*.js")) + sorted((ROOT / "web").glob("*.css"))
    css = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
    reference = (ROOT / "docs" / "design-reference.html").read_text(encoding="utf-8")
    reference_style = re.search(r"<style>\s*\n(.*?)</style>", reference, re.S).group(1)
    code = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "routes").glob("*.py"))
    tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
    checks = {
        "세션없는_API는_401(예외_목록만_열림)": not unguarded,
        "남의_항목_피드백_거부": other_item.status_code == 403,
        "남의_피드백_메모_거부": other_note.status_code == 403,
        "남의_날짜_브리핑은_빈결과": other_day["count"] == 0 and not other_day["exists"] and own_day["count"] == 1,
        "모든_화면_뷰포트_메타": all('name="viewport"' in p.read_text(encoding="utf-8") for p in pages),
        "디자인_참고파일_style_그대로·640px_이하_한줄": css.startswith(reference_style) and "@media (max-width:640px)" in css,
        "화면_긴줄표_없음": not [p.name for p in web_files if chr(0x2014) in p.read_text(encoding="utf-8")],
        "외부_스크립트·프레임워크_없음": not [p.name for p in pages if re.search(r'<script[^>]+src="https?://', p.read_text(encoding="utf-8"))],
        "SSE_없음": "text/event-stream" not in code and "EventSource" not in "".join(p.read_text(encoding="utf-8") for p in web_files),
        "공개_MCP_도구_없음": not tool_names & {"get_briefing", "ask_briefing", "get_tool_verification"},
    }
    checks["API_경로를_모두_셈"] = len(routes) >= 20
    report = {"checks": checks, "api_routes": len(routes), "statuses": statuses, "open_routes": OPEN, "unguarded": unguarded, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
