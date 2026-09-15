"""발송 검수 (계획안 9.2 W1 08:00 발송 멱등, 부록 B 6, 뼈대 완성 정의 "카드마다 trace_id").

실행: uv run python -m tests.pipeline.check_deliver
- 렌더링: 카드 전체·trace_id·뉴스/도구 칸·"오늘 새 도구 없음"·빈 행·이스케이프·위험 링크 차단
- DB(날짜 2000-01-02로 넣고 끝나면 지움): 발송함 → sent_at 기록 → 다시 불러도 0통(멱등), 개발 모드는 is_test만
- API(uvicorn 실제 기동): 서비스 키 없으면 401, 발송함·발송 기록·상태
실제 메일은 보내지 않는다 (개발 모드).
"""
import json
import os
import sys
from datetime import date

import httpx
from sqlalchemy import delete, insert, select

import db
import memory
import models
from pipeline import briefing_mail, deliver
from tests.app.check_main import KEY, free_port, start

DAY = date(2000, 1, 2)
HOST = "https://example.test/deliver/"


def card(n: int, kind: str, **extra) -> dict:
    return {"item_id": None, "type": kind, "title": f"검수 카드 {n}", "url": f"{HOST}{n}", "summary_ko": f"요약 {n}",
            "for_me": f"나한테는 {n}", "why_this_card": f"이유 {n}", "source_checked": True, "notice": None,
            "pros": [{"text": "장점", "evidence_url": f"{HOST}{n}"}], "cons": [], "install_cmd": None,
            "trace_id": f"trace-{n}", "rank": n} | extra


def render_checks() -> dict:
    hostile = card(1, "news", title='<script>alert(1)</script>', url="javascript:alert(1)", summary_ko="A & B <b>",
                   notice="원문 확인 필요")
    tool = card(2, "mcp", install_cmd="npx -y @example/mcp")
    mixed = briefing_mail.render(DAY, "자바 백엔드 개발자", [hostile, tool])
    news_only = briefing_mail.render(DAY, "마케터", [card(3, "news")])
    empty = briefing_mail.render(DAY, "마케터", [], "후보 3건 모두 빠짐 (반려 3, 검증 제외 0, 형식 실패 0)")
    return {
        "제목_날짜·카드수": mixed["subject"] == "[toolscout] 1월 2일 AI 브리핑 · 카드 2장",
        "카드마다_trace_id(HTML·텍스트)": all(t in mixed["html"] and t in mixed["text"] for t in ("trace-1", "trace-2")),
        "카드_전체_필드": all(s in mixed["html"] for s in ("요약", "나한테는", "이 카드인 이유", "장점", "설치:", "원문 확인 필요")),
        "제목·요약_이스케이프": "<script>" not in mixed["html"] and "&lt;script&gt;" in mixed["html"] and "A &amp; B &lt;b&gt;" in mixed["html"],
        "javascript_링크_차단": "javascript:" not in mixed["html"],
        "뉴스·도구_칸": "뉴스</h2>" in mixed["html"] and "새 MCP·스킬</h2>" in mixed["html"],
        "도구_없으면_오늘_새_도구_없음": briefing_mail.NO_TOOLS in news_only["html"] and briefing_mail.NO_TOOLS in news_only["text"],
        "빈_행이면_오늘_볼_만한_게_없었음": briefing_mail.EMPTY_TITLE in empty["subject"] and "반려 3" in empty["html"] and "반려 3" in empty["text"],
    }


def seed(user_ids: list[int]) -> None:
    cleanup()
    with db.get_engine().begin() as c:
        item_ids = []
        for n, kind in ((1, "news"), (2, "mcp")):
            item_ids.append(c.execute(insert(db.Item).values(date=DAY, type=kind, title=f"검수 카드 {n}", url=f"{HOST}{n}",
                                                             source="test").returning(db.Item.id)).scalar_one())
        backend, marketer = user_ids
        for rank, (item_id, kind) in enumerate(zip(item_ids, ("news", "mcp")), 1):
            c.execute(insert(db.Briefing).values(user_id=backend, date=DAY, item_id=item_id, rank=rank,
                                                 card_json=card(rank, kind, item_id=item_id), trace_id=f"trace-{rank}"))
        c.execute(insert(db.Briefing).values(user_id=marketer, date=DAY, item_id=None, rank=0, card_json=None,
                                             empty_reason="후보 2건 모두 빠짐 (반려 2, 검증 제외 0, 형식 실패 0)", trace_id="trace-empty"))


def cleanup() -> None:
    with db.get_engine().begin() as c:
        c.execute(delete(db.Briefing).where(db.Briefing.date == DAY))
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def db_checks(user_ids: list[int]) -> dict:
    seed(user_ids)
    first = deliver.outbox(DAY)
    marked = deliver.mark_sent([m["user_id"] for m in first], DAY)
    again = deliver.outbox(DAY)
    marked_again = deliver.mark_sent(user_ids, DAY)
    with db.get_engine().connect() as c:
        sent_rows = c.execute(select(db.Briefing.sent_at).where(db.Briefing.date == DAY)).all()
    by_user = {m["user_id"]: m for m in first}
    return {
        "발송함_사용자별_한통": sorted(by_user) == sorted(user_ids),
        "백엔드_카드2·trace_id": by_user[user_ids[0]]["cards"] == 2 and by_user[user_ids[0]]["trace_ids"] == ["trace-1", "trace-2"],
        "마케터_빈행_메일": by_user[user_ids[1]]["cards"] == 0 and briefing_mail.EMPTY_TITLE in by_user[user_ids[1]]["subject"],
        "받는사람_users.email": by_user[user_ids[0]]["to"].endswith(".test"),
        "sent_at_기록_3행": marked == 3 and all(r[0] is not None for r in sent_rows),
        "다시_불러도_0통(멱등)": again == [] and marked_again == 0,
    }


def api_checks(user_ids: list[int]) -> dict:
    seed(user_ids)
    port = free_port()
    os.environ["MCP_SERVICE_KEY"] = KEY
    proc = start(port)
    base = f"http://127.0.0.1:{port}/api/w1"
    headers = {"X-Service-Key": KEY}
    try:
        no_key = httpx.get(f"{base}/outbox", params={"date": str(DAY)}, timeout=10)
        wrong_key = httpx.get(f"{base}/status", headers={"X-Service-Key": "wrong-key"}, timeout=10)
        box = httpx.get(f"{base}/outbox", params={"date": str(DAY)}, headers=headers, timeout=30).json()
        sent = httpx.post(f"{base}/sent", json={"date": str(DAY), "user_ids": user_ids}, headers=headers, timeout=30).json()
        box_again = httpx.get(f"{base}/outbox", params={"date": str(DAY)}, headers=headers, timeout=30).json()
        state = httpx.get(f"{base}/status", headers=headers, timeout=10).json()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    return {
        "API_키없으면_401": no_key.status_code == 401 and wrong_key.status_code == 401,
        "API_발송함_dev_mode·2통·HTML": box["dev_mode"] is True and box["count"] == 2 and all(m["html"] and m["text"] for m in box["messages"]),
        "API_발송기록·다시_0통": sent["rows_marked"] == 3 and box_again["count"] == 0,
        "API_상태_실행중_아님": state == {"running": False, "last": None},
    }


def main() -> int:
    user_ids = memory.test_user_ids()
    try:
        checks = {"개발_모드": models.dev_mode(), **render_checks(), **db_checks(user_ids), **api_checks(user_ids)}
    finally:
        cleanup()
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
