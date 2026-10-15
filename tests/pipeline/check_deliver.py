"""발송 검수 (계획안 9.2 W1 08:00 발송 멱등, 부록 B 6, 뼈대 완성 정의 "카드마다 trace_id").

실행: uv run python -m tests.pipeline.check_deliver
- 렌더링: 카드 전체·trace_id·뉴스/도구 칸·"오늘 새 도구 없음"·빈 행·이스케이프·위험 링크 차단
- DB(날짜 2000-01-02로 넣고 끝나면 지움): 발송함 → sent_at 기록 → 다시 불러도 0통(멱등), 개발 모드는 is_test만
- 발송(가짜 SMTP): 모든 모드에서 사용자마다 한 통(보낸 사용자만 sent_at, 한 통 실패는 그 사용자만 미발송). 개발 모드의 가짜 테스트 프로필은
  ADMIN_EMAILS로 가고 제목 앞에 [테스트 프로필 직군], 개발자 본인 계정은 본인 주소·운영과 같은 제목(2026-09-28, 묶음 메일 없앰). 설정 없으면 기록 안 함
- 실패 알림(W4): ADMIN_EMAILS에 한 통, 메일 설정·받는 사람이 없으면 보내지 않고 결과만 / DB 깨우기 접속
- API(uvicorn 실제 기동, 예약 꺼짐): 서비스 키 없으면 401, 상태
실제 메일은 보내지 않는다.
"""
import json
import os
import smtplib
import sys
from datetime import date

import httpx
from sqlalchemy import delete, insert, select, update

import db
import memory
import models
from pipeline import briefing_mail, deliver, persist
from tests.app.check_main import KEY, free_port, start


class FakeSMTP:
    """smtplib.SMTP_SSL 대신. 제목에 fail_subject가 들어 있으면 발송 실패를 낸다."""
    sent: list = []
    logins: list = []
    fail_subject: str | None = None

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        FakeSMTP.logins.append(bool(user and password))

    def send_message(self, message):
        if FakeSMTP.fail_subject and FakeSMTP.fail_subject in message["Subject"]:
            raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"refused")})
        FakeSMTP.sent.append({"to": message["To"], "subject": message["Subject"], "from": message["From"],
                              "parts": [p.get_content_type() for p in message.iter_parts()]})

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
    monday = briefing_mail.render(DAY, "마케터", [card(3, "news"), tool, card(4, "mcp") | {"related": True, "title": "관련 도구 카드"}])
    return {
        "제목_날짜·카드수": mixed["subject"] == "[toolscout] 1월 2일 AI 브리핑 · 카드 2장",
        "카드마다_trace_id(HTML·텍스트)": all(t in mixed["html"] and t in mixed["text"] for t in ("trace-1", "trace-2")),
        # 2026-10-14 2차 리디자인(3장): 메일 카드는 나에게·좋은 점·$ 명령·원문 확인 필요 배지. '이 카드인 이유'는 메일에 넣지 않는다
        "카드_전체_필드": all(s in mixed["html"] for s in ("요약", "나에게", "좋은 점", "npx -y @example/mcp", "원문 확인 필요"))
        and "이 카드인 이유" not in mixed["html"],
        "제목·요약_이스케이프": "<script>" not in mixed["html"] and "&lt;script&gt;" in mixed["html"] and "A &amp; B &lt;b&gt;" in mixed["html"],
        "javascript_링크_차단": "javascript:" not in mixed["html"],
        "뉴스·도구_칸": ">뉴스 <span" in mixed["html"] and ">새 MCP·스킬 <span" in mixed["html"] and "== 뉴스 ==" in mixed["text"],
        "도구_없으면_오늘_새_도구_없음": briefing_mail.NO_TOOLS in news_only["html"] and briefing_mail.NO_TOOLS in news_only["text"],
        "관련카드는_따로_칸(없으면_칸없음)": f">{briefing_mail.RELATED_TITLE}</td>" in monday["html"]
        and f"== {briefing_mail.RELATED_TITLE} ==" in monday["text"] and briefing_mail.RELATED_TITLE not in mixed["html"]
        and monday["html"].index("관련 도구 카드") > monday["html"].index(briefing_mail.RELATED_TITLE),
        "빈_행이면_오늘_볼_만한_게_없었음": briefing_mail.EMPTY_TITLE in empty["subject"] and "반려 3" in empty["html"] and "반려 3" in empty["text"],
        "trace_id_헤더_한_줄": deliver.build_email(mixed | {"trace_ids": ["trace-1", "trace-2"]}, "me@example.test", ["a@example.test"])
        ["X-Toolscout-Trace"] == "trace-1,trace-2",
        **address_checks(mixed),
    }


def address_checks(mixed: dict) -> dict:
    """받는 사람·제목 (2026-09-28 사용자 결정 "실전으로 갈 거라 메일도 다 수정해": 개발 모드 묶음 메일 없앰)."""
    admins = ["me@example.test", "other@example.test"]
    own_mail, own_to = deliver.addressed(mixed | {"to": "ME@example.test", "role": "개발자"}, True, admins)
    fake_mail, fake_to = deliver.addressed(mixed | {"to": "test-backend@toolscout.test", "role": "자바 백엔드 개발자"}, True, admins)
    prod_mail, prod_to = deliver.addressed(mixed | {"to": "user@example.test", "role": "개발자"}, False, admins)
    return {
        "본인계정은_본인주소·운영과_같은_제목": own_to == ["ME@example.test"] and own_mail["subject"] == mixed["subject"],
        "가짜프로필은_관리자에게·[테스트 프로필 직군]": fake_to == admins
        and fake_mail["subject"] == f"[테스트 프로필 자바 백엔드 개발자] {mixed['subject']}",
        "운영모드는_사용자주소·제목_그대로": prod_to == ["user@example.test"] and prod_mail["subject"] == mixed["subject"],
        "묶음메일_없음": not hasattr(briefing_mail, "combine") and "개발 모드" not in mixed["html"] + mixed["subject"],
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


def send_checks(user_ids: list[int]) -> dict:
    """가짜 SMTP로 send_day. 환경변수는 이 함수 안에서만 바꾸고 되돌린다 (값은 가짜)."""
    keys = ("GMAIL_USER", "GMAIL_APP_PASSWORD", "ADMIN_EMAILS")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ.update({"GMAIL_USER": "sender@example.test", "GMAIL_APP_PASSWORD": "fakepassword0000",
                           "ADMIN_EMAILS": "me@example.test, other-admin@example.test"})
        seed(user_ids)
        FakeSMTP.sent, FakeSMTP.logins, FakeSMTP.fail_subject = [], [], "[테스트 프로필 자바 백엔드 개발자]"
        failed_all = deliver.send_day(DAY, smtp_factory=FakeSMTP)  # 백엔드 한 통만 실패, 마케터는 나간다
        remaining = deliver.outbox(DAY)
        FakeSMTP.fail_subject = None
        retry = deliver.send_day(DAY, smtp_factory=FakeSMTP)
        after_all = deliver.send_day(DAY, smtp_factory=FakeSMTP)
        seed(user_ids)
        os.environ["GMAIL_APP_PASSWORD"] = ""
        missing = deliver.send_day(DAY, smtp_factory=FakeSMTP)
        missing_left = len(deliver.outbox(DAY))
        os.environ["ADMIN_EMAILS"] = ""
        console = deliver.send_day(DAY, smtp_factory=FakeSMTP)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    one_mail = FakeSMTP.sent[0] if FakeSMTP.sent else {}
    return {
        "개발모드_가짜프로필은_ADMIN_EMAILS로": all(m["to"] == "me@example.test, other-admin@example.test" for m in FakeSMTP.sent),
        "개발모드도_사용자마다_한통": len(FakeSMTP.sent) == 2 and retry["mails"] == 1 and retry["sent"] == [user_ids[0]],
        "개발모드_가짜프로필_제목에_[테스트 프로필]": all(m["subject"].startswith("[테스트 프로필 ") and "[개발 모드]" not in m["subject"]
                                                   for m in FakeSMTP.sent),
        "텍스트·HTML_둘다": one_mail.get("parts") == ["text/plain", "text/html"],
        "한통_실패는_그_사용자만_미발송": failed_all["mode"] == "smtp" and failed_all["sent"] == [user_ids[1]]
        and [f["user_id"] for f in failed_all["failed"]] == [user_ids[0]] and [m["user_id"] for m in remaining] == [user_ids[0]],
        "다시_보내면_남은_사용자만": after_all["messages"] == 0,
        "메일설정_없으면_기록안함": missing["mode"] == "config_missing" and missing_left == 2 and not missing["sent"],
        "ADMIN_EMAILS_없으면_콘솔·DB만": console["mode"] == "console" and console["rows_marked"] == 3,
        **prod_checks(user_ids),
    }


def prod_checks(user_ids: list[int]) -> dict:
    """운영 모드(DEV_MODE=0)는 전과 같이 사용자마다 각자 한 통. 환경변수는 여기서만 바꾸고 되돌린다."""
    keys = ("GMAIL_USER", "GMAIL_APP_PASSWORD", "ADMIN_EMAILS", "DEV_MODE")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ.update({"GMAIL_USER": "sender@example.test", "GMAIL_APP_PASSWORD": "fakepassword0000",
                           "ADMIN_EMAILS": "me@example.test", "DEV_MODE": "0"})
        # 운영 모드 발송은 승인된 실제 사용자·관리자만 받는다. 검수 동안만 두 프로필을 실제 사용자처럼 두고 끝나면 되돌린다
        with db.get_engine().begin() as c:
            before = {r.id: (r.status, r.is_test) for r in c.execute(select(db.User.id, db.User.status, db.User.is_test).where(db.User.id.in_(user_ids)))}
            c.execute(update(db.User).where(db.User.id.in_(user_ids)).values(status="approved", is_test=False))
        seed(user_ids)
        blocked_ids, test_ids = _excluded_in_prod(user_ids)
        FakeSMTP.sent, FakeSMTP.fail_subject = [], briefing_mail.EMPTY_TITLE  # 마케터(빈 행)만 실패
        partial = deliver.send_day(DAY, smtp_factory=FakeSMTP)
        remaining = deliver.outbox(DAY)
        FakeSMTP.fail_subject = None
        retry = deliver.send_day(DAY, smtp_factory=FakeSMTP)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        with db.get_engine().begin() as c:
            for uid, (status, is_test) in before.items():
                c.execute(update(db.User).where(db.User.id == uid).values(status=status, is_test=is_test))
    return {
        "운영모드_차단·가짜프로필은_발송_안함": blocked_ids == [] and test_ids == [],
        "운영모드_사용자마다_각자_한통": partial["mails"] == 2 and all(m["to"].endswith(".test") and "[개발 모드]" not in m["subject"]
                                                     for m in FakeSMTP.sent),
        "운영모드_실패한_사용자만_남음": partial["sent"] == [user_ids[0]] and [f["user_id"] for f in partial["failed"]] == [user_ids[1]]
        and [m["user_id"] for m in remaining] == [user_ids[1]] and retry["sent"] == [user_ids[1]],
    }


def _excluded_in_prod(user_ids: list[int]) -> tuple[list[int], list[int]]:
    """운영 모드에서 차단된 사용자, 관리자 아닌 가짜 프로필(is_test)은 발송함에 안 나온다. 확인 뒤 승인·실제 사용자로 되돌린다."""
    first = user_ids[0]
    with db.get_engine().begin() as c:
        c.execute(update(db.User).where(db.User.id == first).values(status="blocked"))
    blocked = [m["user_id"] for m in deliver.outbox(DAY) if m["user_id"] == first]
    with db.get_engine().begin() as c:
        c.execute(update(db.User).where(db.User.id == first).values(status="approved", is_test=True))
    test = [m["user_id"] for m in deliver.outbox(DAY) if m["user_id"] == first]
    with db.get_engine().begin() as c:
        c.execute(update(db.User).where(db.User.id == first).values(is_test=False))
    return blocked, test


def alert_checks() -> dict:
    """실패 알림(W4)과 DB 깨우기. 가짜 SMTP, 환경변수는 가짜 값으로 바꿨다가 되돌린다."""
    keys = ("GMAIL_USER", "GMAIL_APP_PASSWORD", "ADMIN_EMAILS")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ.update({"GMAIL_USER": "sender@example.test", "GMAIL_APP_PASSWORD": "fakepassword0000", "ADMIN_EMAILS": "me@example.test"})
        FakeSMTP.sent, FakeSMTP.fail_subject = [], None
        sent = deliver.send_alert("09월 16일 하루 실행 실패", ["하루 실행을 3번 시도했지만 끝내지 못했어요."], smtp_factory=FakeSMTP)
        mail = FakeSMTP.sent[-1] if FakeSMTP.sent else {}
        os.environ["GMAIL_APP_PASSWORD"] = ""
        mail_error = deliver.send_alert("검수", ["검수"], smtp_factory=FakeSMTP)
        os.environ["ADMIN_EMAILS"] = ""
        no_admin = deliver.send_alert("검수", ["검수"], smtp_factory=FakeSMTP)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    try:
        persist.wake_db()
        woke = True
    except Exception:
        woke = False
    return {
        "실패알림_ADMIN_EMAILS에_한통": sent == "sent" and mail.get("to") == "me@example.test"
        and mail.get("subject") == "[toolscout 실패 알림] 09월 16일 하루 실행 실패",
        "실패알림_메일설정없으면_mail_error·ADMIN없으면_no_admin": mail_error == "mail_error" and no_admin == "no_admin",
        "DB_깨우기_접속": woke,
    }


def api_checks() -> dict:
    port = free_port()
    os.environ["MCP_SERVICE_KEY"] = KEY
    proc = start(port)
    base = f"http://127.0.0.1:{port}/api/w1"
    headers = {"X-Service-Key": KEY}
    try:
        no_key = httpx.post(f"{base}/send", params={"date": str(DAY)}, timeout=10)
        wrong_key = httpx.get(f"{base}/status", headers={"X-Service-Key": "wrong-key"}, timeout=10)
        state = httpx.get(f"{base}/status", headers=headers, timeout=10).json()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    return {
        "API_키없으면_401": no_key.status_code == 401 and wrong_key.status_code == 401,
        "API_상태_예약꺼짐·실행중아님": state["enabled"] is False and state["running"] is False and state["last_run"] is None,
    }


def main() -> int:
    user_ids = memory.test_user_ids()[:2]  # 프로필 A·B만 쓴다
    try:
        checks = {"개발_모드": models.dev_mode(), **render_checks(), **db_checks(user_ids), **send_checks(user_ids), **alert_checks(), **api_checks()}
    finally:
        cleanup()
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
