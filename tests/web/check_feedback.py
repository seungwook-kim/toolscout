"""피드백(W3) 검수: 웹 세션 버튼 3종, 재클릭 취소, -5에서 멈춤, 사유·메모, 다른 사용자 항목 거부, 메일 서명 링크(1회용·만료·위조).

실행: uv run python -m tests.web.check_feedback
모델 호출 없음. 검수용 사용자·항목은 끝나면 지운다.
"""
import json
import sys
from datetime import date

from tests.web import common

from sqlalchemy import delete, insert, select  # noqa: E402

import db  # noqa: E402
from pipeline import briefing_mail  # noqa: E402
from routes import tokens  # noqa: E402
from routes.feedback import feedback_link  # noqa: E402

A, B = "web-fb-a@toolscout.test", "web-fb-b@toolscout.test"
HOST = "https://example.test/web-fb/"
DAY = date(2000, 1, 7)


def seed(a_id: int, b_id: int) -> list[int]:
    specs = [(1, "news", "pricing"), (2, "mcp", "mcp_tools"), (3, "news", "pricing"), (4, "news", "pricing"), (5, "news", "industry")]
    with db.get_engine().begin() as c:
        ids = [c.execute(insert(db.Item).values(date=DAY, type=k, topic=t, title=f"피드백 검수 {n}", url=f"{HOST}{n}", source="test")
                         .returning(db.Item.id)).scalar_one() for n, k, t in specs]
        for rank, item_id in enumerate(ids[:4], 1):
            c.execute(insert(db.Briefing).values(user_id=a_id, date=DAY, item_id=item_id, rank=rank, trace_id="t",
                                                 card_json={"item_id": item_id, "type": specs[rank - 1][1], "title": "x"}))
        c.execute(insert(db.Briefing).values(user_id=b_id, date=DAY, item_id=ids[4], rank=1, trace_id="t",
                                             card_json={"item_id": ids[4], "type": "news", "title": "x"}))
    return ids


def weight(user_id: int, topic: str) -> int | None:
    with db.get_engine().connect() as c:
        return c.execute(select(db.Weight.weight).where(db.Weight.user_id == user_id, db.Weight.topic == topic)).scalar()


def feedback_rows(user_id: int) -> list[tuple]:
    with db.get_engine().connect() as c:
        return c.execute(select(db.Feedback.item_id, db.Feedback.action, db.Feedback.reason, db.Feedback.memo)
                         .where(db.Feedback.user_id == user_id).order_by(db.Feedback.id)).all()


def cleanup() -> None:
    common.cleanup_users("web-fb-")
    with db.get_engine().begin() as c:
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def main() -> int:
    cleanup()
    try:
        with common.client() as c:
            common.login(c, A)
            c.post("/api/profile", json={"role": "개발자", "weights": {"pricing": -3}})
            cb = common.second_client()
            common.login(cb, B)
            a_id, b_id = common.user_id(A), common.user_id(B)
            ids = seed(a_id, b_id)
            with db.get_engine().begin() as conn:  # 프로필 저장이 넣은 가중치 중 pricing을 -3으로
                conn.execute(delete(db.Weight).where(db.Weight.user_id == a_id, db.Weight.topic == "pricing"))
                conn.execute(insert(db.Weight).values(user_id=a_id, topic="pricing", weight=-3))
            not_interested = c.post("/api/feedback", json={"item_id": ids[0], "action": "관심없음"}).json()
            w_after_1 = weight(a_id, "pricing")
            cancelled = c.post("/api/feedback", json={"item_id": ids[0], "action": "관심없음"}).json()
            w_after_cancel = weight(a_id, "pricing")
            c.post("/api/feedback", json={"item_id": ids[0], "action": "관심없음"})
            c.post("/api/feedback", json={"item_id": ids[2], "action": "관심없음"})
            clamped = c.post("/api/feedback", json={"item_id": ids[3], "action": "관심없음"}).json()
            w_clamped = weight(a_id, "pricing")
            cancel_clamped = c.post("/api/feedback", json={"item_id": ids[3], "action": "관심없음"}).json()
            w_after_cancel_clamped = weight(a_id, "pricing")
            mcp_before = weight(a_id, "mcp_tools")
            tried = c.post("/api/feedback", json={"item_id": ids[1], "action": "써봤음"}).json()
            memo = c.post(f"/api/feedback/{tried['feedback_id']}/note", json={"memo": "설치 잘 됨"})
            weird = c.post("/api/feedback", json={"item_id": ids[1], "action": "이상함"}).json()
            reason = c.post(f"/api/feedback/{weird['feedback_id']}/note", json={"reason": "사실 틀림"})
            bad_reason = c.post(f"/api/feedback/{weird['feedback_id']}/note", json={"reason": "그냥"})
            other_item = c.post("/api/feedback", json={"item_id": ids[4], "action": "관심없음"})
            other_note = cb.post(f"/api/feedback/{weird['feedback_id']}/note", json={"reason": "사실 틀림"})
            bad_action = c.post("/api/feedback", json={"item_id": ids[1], "action": "좋아요"})
            c.cookies.clear()
            session_required = c.post("/api/feedback", json={"item_id": ids[1], "action": "관심없음"})
            rows_before_links = len(feedback_rows(b_id))
            b_link = feedback_link(b_id, ids[4], "이상함").split("t=", 1)[1]
            from urllib.parse import unquote

            b_token = unquote(b_link)
            link_ok = c.post("/api/feedback/link", json={"token": b_token}).json()
            link_note = c.post("/api/feedback/link/note", json={"token": link_ok.get("note_token", ""), "reason": "번역 어색"})
            link_again = c.post("/api/feedback/link", json={"token": b_token})
            expired = c.post("/api/feedback/link", json={"token": tokens.sign("feedback", {"u": b_id, "i": ids[4], "a": "관심없음"}, -1)})
            forged = c.post("/api/feedback/link", json={"token": b_token[:-4] + "abcd"})
            other_user_link = c.post("/api/feedback/link", json={"token": tokens.sign("feedback", {"u": b_id, "i": ids[0], "a": "관심없음"}, 600)})
            rows_b = feedback_rows(b_id)
            f_page = c.get(f"/f?t={b_link}")
            card = {"item_id": ids[1], "type": "mcp", "title": "도구", "url": f"{HOST}2", "summary_ko": "요약", "for_me": "나", "why_this_card": "이유",
                    "trace_id": "t", "pros": [], "cons": []}
            mail = briefing_mail.render(DAY, "개발자", [card], links=lambda cd, action: feedback_link(a_id, cd["item_id"], action))
    finally:
        cleanup()
    checks = {
        "관심없음은_주제_-1·문구": not_interested["status"] == "recorded" and w_after_1 == -4
        and not_interested["message"] == "내일부터 가격·요금·한도 주제는 뒤로 뺄게요",
        "같은_버튼_재클릭은_취소·원복": cancelled["status"] == "cancelled" and w_after_cancel == -3,
        "-5에서_멈춤·취소해도_그대로": w_clamped == -5 and clamped["weight"] == -5 and "보여 드리지 않을게요" in clamped["message"]
        and cancel_clamped["status"] == "cancelled" and w_after_cancel_clamped == -5,
        "써봤음은_주제_+1·메모": tried["status"] == "recorded" and tried["weight"] == (mcp_before or 0) + 1 and memo.status_code == 200,
        "이상함은_가중치_그대로·사유_3택": weird["status"] == "recorded" and reason.status_code == 200 and bad_reason.status_code == 400,
        "다른_사용자_항목·피드백_거부": other_item.status_code == 403 and other_note.status_code == 403,
        "없는_버튼_값은_400": bad_action.status_code == 400,
        "세션없으면_401": session_required.status_code == 401,
        "메일_링크_기록·사유": link_ok["status"] == "recorded" and link_note.status_code == 200
        and [tuple(r) for r in rows_b] == [(ids[4], "이상함", "번역 어색", None)] and rows_before_links == 0,
        "메일_링크_1회용": link_again.status_code == 400 and "이미" in link_again.json()["detail"],
        "만료·위조_링크는_안내·기록없음": expired.status_code == 400 and expired.json()["detail"] == "링크가 만료됐어요"
        and forged.status_code == 400 and forged.json()["detail"] == "링크가 만료됐어요" and len(rows_b) == 1,
        "링크여도_남의_브리핑_항목은_거부": other_user_link.status_code == 403,
        "f_화면_열림": f_page.status_code == 200 and "/api/feedback/link" in f_page.text,
        "메일_카드에_버튼_3종_서명링크": mail["html"].count("/f?t=") == 3 and all(a in mail["text"] for a in ("[써봤음]", "[관심없음]", "[이상함]")),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
