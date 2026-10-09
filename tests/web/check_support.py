"""고객센터 푸터·운영정책·문의 검수 (2026-10-09). 모델 호출 없음, 메일은 가짜 폴더(MAIL_FAKE_DIR)로만 받는다.

실행: uv run python -m tests.web.check_support
- 푸터: web/app.js의 TS.footer가 네 링크(운영정책·이용약관·개인정보처리방침 굵게·고객센터 문의하기)와 © 2026 toolscout을 만들고,
  TS.frame이 부르며 TS.shell·TS.bare가 둘 다 TS.frame을 부른다. 모든 화면이 shell 또는 bare를 쓴다. 로그인·가입의 예전 작은 링크는 없어짐
- /policy·/support: 로그인 없이 200, 색인 허용, robots.txt Allow, 운영정책 필수 항목, 개인정보처리방침의 문의 안내가 /support로 바뀜
- POST /api/support: 저장, 관리자 메일 1통(제목·문의자 이메일·내용·Reply-To), 문의자에게는 메일 0통, 형식 오류 400, 길이 제한,
  비로그인 1시간 3건 넘으면 429, 로그인 1시간 10건, 꿀단지(저장 안 함), 같은 내용 연속 중복, 메일 실패해도 저장
- 관리자 목록·처리함: 관리자만(일반 403, 비로그인 401)
검수가 만든 문의 행과 검수용 사용자는 끝에 지운다.
"""
import json
import os
import re
import sys
from pathlib import Path

from tests.web import common

from sqlalchemy import delete  # noqa: E402
from sqlmodel import select  # noqa: E402

import db  # noqa: E402
from pipeline import deliver  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"
ADMIN, USER = "web-sup-admin@toolscout.test", "web-sup-user@toolscout.test"
ASKER = "web-sup-asker@toolscout.test"
LONG_OK = "가" * 2000


def rows() -> list:
    with db.session() as s:
        return list(s.exec(select(db.SupportMessage).where(db.SupportMessage.email.like("web-sup-%@toolscout.test")).order_by(db.SupportMessage.id)).all())


def clean() -> None:
    with db.get_engine().begin() as conn:
        conn.execute(delete(db.SupportMessage).where(db.SupportMessage.email.like("web-sup-%@toolscout.test")))
        ids = [r[0] for r in conn.execute(select(db.User.id).where(db.User.email.like("web-sup-%@toolscout.test")))]
        if ids:
            conn.execute(delete(db.SupportMessage).where(db.SupportMessage.user_id.in_(ids)))
    common.cleanup_users("web-sup-")


def post(c, body: dict, who: str = "a"):
    """who마다 접속 주소·브라우저 값을 달리 해서 스팸 제한이 서로 안 섞이게 한다."""
    payload = {"email": ASKER, "category": "account", "body": "로그인이 안 돼요. 확인 부탁드립니다.", "website": "", **body}
    return c.post("/api/support", json=payload, headers={"x-forwarded-for": f"198.51.100.{ord(who[0]) % 200}", "user-agent": f"check-support-{who}"})


def support_mails() -> list[dict]:
    return [m for m in common.mails() if m["subject"].startswith("[toolscout 문의]")]


def footer_checks() -> dict:
    js = (WEB / "app.js").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    block = js.split("footer() {", 1)[1].split("\n  },", 1)[0] if "footer() {" in js else ""
    frame = js.split("frame(barHtml) {", 1)[1].split("\n  },", 1)[0]
    bare = js.split("bare({", 1)[1].split("\n  },", 1)[0]
    shell = js.split("async shell(", 1)[1].split("\n  },", 1)[0]
    pages = {p.name: p.read_text(encoding="utf-8") for p in WEB.glob("*.html")}
    no_bar = [n for n, t in pages.items() if "TS.shell(" not in t and "TS.bare(" not in t]
    login, signup = pages["login.html"], pages["signup.html"]
    return {
        "푸터_네_링크": all(f'href="{h}"' in block for h in ("/policy", "/terms", "/privacy", "/support")),
        "푸터_글자": all(s in block for s in ("운영정책", "이용약관", "개인정보처리방침", "고객센터 문의하기", "© 2026 toolscout")),
        "푸터_개인정보처리방침만_굵게": 'class="strong" href="/privacy"' in block and block.count('class="strong"') == 1 and ".site-foot a.strong{font-weight:700" in css,
        "푸터_nav_이름": 'aria-label="정책과 문의"' in block,
        "frame이_푸터를_붙임": "TS.footer()" in frame,
        "shell·bare_모두_frame을_부름": "TS.frame(" in shell and "TS.frame(" in bare,
        "모든_화면이_shell_또는_bare": not no_bar,
        "탭바·고정바에_안_가림(css)": ".has-tabbar .site-foot" in css and ".has-ctabar .site-foot" in css and "body.has-savebar .site-foot" in css,
        "푸터_색은_토큰만": not re.search(r"\.site-foot[^{]*\{[^}]*#[0-9A-Fa-f]{3,6}", css),
        "로그인·가입의_예전_링크_정리": 'class="legal"' not in login and 'class="legal"' not in signup and ".legal" not in css,
        "함정_링크_그대로": 'href="/archive/full-index"' in login and 'tabindex="-1"' in login,
    }


def main() -> int:
    common.admin_emails(ADMIN, USER)
    saved_admins = os.environ.get("ADMIN_EMAILS", "")
    checks: dict = {}
    db.init_db()  # support_messages 표가 없으면 만든다(다른 검수와 같은 방식, 운영 DB에도 생긴다)
    clean()
    with common.client() as c:
        # ----- 푸터 -----
        checks.update(footer_checks())

        # ----- 공개 화면 -----
        policy, support, privacy, terms = c.get("/policy"), c.get("/support"), c.get("/privacy"), c.get("/terms")
        robots = c.get("/robots.txt").text
        checks["policy·support_로그인없이_200"] = policy.status_code == 200 and support.status_code == 200
        checks["색인_허용(noindex_없음)"] = all("noindex" not in r.headers.get("x-robots-tag", "") for r in (policy, support))
        checks["robots_Allow"] = "Allow: /policy" in robots and "Allow: /support" in robots
        checks["운영정책_필수_항목"] = all(s in policy.text for s in ("시행일 2026-10-09", "가입과 승인", "차단", "무단 복제", "크롤링", "AI 학습", "AI 크롤러 차단", "요청 수 제한",
                                                                   "24시간", "워터마크", "틀릴 수 있어요", "이상함", "샌드박스", "한계", "계정 삭제", "기억 지우기", "정책이 바뀔 때"))
        checks["문의_화면_칸"] = all(s in support.text for s in ('type="email"', "계정·로그인", "브리핑·메일", "개인정보·삭제 요청", "기타", 'maxlength="2000"',
                                                                 'name="website"', "/api/support", "/api/me")) and "결제" not in support.text
        checks["방침·약관이_/support로_안내"] = ('href="/support"' in privacy.text and "서비스 안 문의 메일" not in privacy.text and "운영자가 채울 자리" not in privacy.text
                                           and 'href="/support"' in terms.text and "서비스 안 문의 메일" not in terms.text)

        # ----- 문의 보내기 (비로그인) -----
        before = len(support_mails())
        ok = post(c, {}, "a")
        stored = rows()
        sent = support_mails()[before:]
        checks["저장_200"] = ok.status_code == 200 and ok.json().get("ok") is True and len(stored) == 1 and stored[0].email == ASKER and stored[0].user_id is None
        checks["저장값_종류·내용"] = bool(stored) and stored[0].category == "account" and stored[0].body.startswith("로그인이 안 돼요") and len(stored[0].client_hash) == 32
        checks["관리자_메일_1통"] = len(sent) == 1 and sent[0]["subject"] == "[toolscout 문의] 계정·로그인" and ADMIN in sent[0]["to"]
        checks["메일에_문의자_이메일·내용"] = bool(sent) and ASKER in sent[0]["text"] and "로그인이 안 돼요" in sent[0]["text"]
        checks["Reply-To가_문의자"] = bool(sent) and sent[0].get("reply_to") == ASKER
        # ----- 형식·길이 -----
        bad_email = [post(c, {"email": e}, "b").status_code for e in ("", "abc", "a@b", "a b@c.de", "a@b.com\nBcc: x@y.zz", "x" * 250 + "@a.bc")]
        checks["이메일_형식_오류_400"] = set(bad_email) == {400}
        checks["종류_오류_400"] = post(c, {"category": "payment"}, "b").status_code == 400 and post(c, {"category": ""}, "b").status_code == 400
        short, longer = post(c, {"body": "너무 짧음"}, "b"), post(c, {"body": "가" * 2001}, "b")
        checks["길이_10자_미만·2000자_초과_400"] = short.status_code == 400 and longer.status_code == 400 and "10자" in short.json()["detail"] and "2000자" in longer.json()["detail"]
        edge = post(c, {"body": "가" * 10}, "c"), post(c, {"body": LONG_OK}, "c")
        checks["길이_경계(10자·2000자)_통과"] = edge[0].status_code == 200 and edge[1].status_code == 200
        checks["오류는_저장·메일_안_함"] = len(rows()) == 3 and len(support_mails()) - before == 3
        # ----- 비로그인 1시간 3건 -----
        results = [post(c, {"body": f"스팸 제한 검수 {i}번째 문의입니다"}, "d").status_code for i in range(5)]
        limited = post(c, {"body": "스팸 제한 검수 마지막 문의입니다"}, "d")
        checks["비로그인_1시간_3건_넘으면_429"] = results == [200, 200, 200, 429, 429] and limited.status_code == 429 and "1시간" in limited.json()["detail"] and "3건" in limited.json()["detail"]
        checks["429는_저장_안_함"] = len([r for r in rows() if r.body.startswith("스팸 제한")]) == 3
        checks["다른_클라이언트는_영향_없음"] = post(c, {"body": "다른 사람이 보내는 문의입니다"}, "e").status_code == 200
        # ----- 꿀단지 -----
        n_rows, n_mails = len(rows()), len(support_mails())
        trap = post(c, {"website": "http://spam.example", "body": "꿀단지 칸이 채워진 문의입니다"}, "f")
        checks["꿀단지_성공처럼_답하고_저장·메일_없음"] = trap.status_code == 200 and trap.json().get("ok") is True and len(rows()) == n_rows and len(support_mails()) == n_mails
        # ----- 중복 -----
        first, again = post(c, {"body": "같은 내용을 두 번 보내 봅니다"}, "g"), post(c, {"body": "같은 내용을 두 번 보내 봅니다"}, "g")
        other = post(c, {"body": "이번에는 다른 내용을 보냅니다"}, "g")
        same = [r for r in rows() if r.body == "같은 내용을 두 번 보내 봅니다"]
        checks["같은_내용_연속_중복은_한_번만"] = first.status_code == again.status_code == 200 and len(same) == 1 and other.status_code == 200
        checks["문의자에게_보낸_메일_0통"] = not [m for m in common.mails() if ASKER in m["to"]]
        # ----- 메일 실패해도 저장 -----
        real_send = deliver.send_single

        def broken(*args, **kwargs):
            raise deliver.MailError("검수용 실패")
        deliver.send_single = broken
        try:
            failed = post(c, {"body": "메일이 실패하는 상황에서 보냅니다"}, "h")
        finally:
            deliver.send_single = real_send
        checks["메일_실패해도_저장·접수"] = failed.status_code == 200 and any(r.body.startswith("메일이 실패하는") for r in rows())

        # ----- 로그인 상태 -----
        common.login(c, USER)
        uid = common.user_id(USER)
        me = c.get("/api/me").json()
        logged = post(c, {"email": USER, "body": "로그인한 상태에서 보낸 문의입니다 1"}, "i")
        mine = [r for r in rows() if r.body.startswith("로그인한 상태에서")]
        checks["로그인_상태는_user_id_저장·me에_이메일"] = logged.status_code == 200 and bool(mine) and mine[0].user_id == uid and me["email"] == USER
        codes = [post(c, {"email": USER, "body": f"로그인한 상태에서 보낸 문의입니다 {n}"}, "i").status_code for n in range(2, 13)]
        checks["로그인_1시간_10건_넘으면_429"] = codes[:9] == [200] * 9 and codes[9] == 429 and codes[10] == 429 and len([r for r in rows() if r.user_id == uid]) == 10

        # ----- 관리자 목록·처리함 -----
        common.login(c, ADMIN)
        listing = c.get("/api/admin/support")
        data = listing.json() if listing.status_code == 200 else {}
        messages = data.get("messages", [])
        target = next((m for m in messages if m["body"].startswith("같은 내용을 두 번")), None)
        checks["관리자_목록"] = listing.status_code == 200 and len(messages) >= 10 and messages[0]["id"] > messages[-1]["id"] and target is not None \
            and {"id", "email", "category_label", "body", "created_at", "handled_at"} <= set(target) and target["handled_at"] is None
        open_before = data.get("open", 0)
        done = c.post(f"/api/admin/support/{target['id']}/handled") if target else None
        after = c.get("/api/admin/support").json()
        checks["처리함_표시"] = bool(done) and done.status_code == 200 and done.json()["handled_at"] is not None and after["open"] == open_before - 1
        checks["처리함_두_번째도_괜찮고_없는_번호_404"] = c.post(f"/api/admin/support/{target['id']}/handled").status_code == 200 and c.post("/api/admin/support/999999999/handled").status_code == 404
        checks["승인_배지에_문의_수_안_넣음"] = "support" not in json.dumps(c.get("/api/me").json())
        # 일반 사용자(관리자 명단에서 뺀 상태)·비로그인은 막힌다
        common.login(c, USER)
        os.environ["ADMIN_EMAILS"] = ",".join(e for e in os.environ["ADMIN_EMAILS"].split(",") if e.strip() and e.strip() != USER)
        normal = [c.get("/api/admin/support").status_code, c.post(f"/api/admin/support/{target['id']}/handled").status_code]
        anon = common.second_client()  # with로 열지 않는다(앱 lifespan은 한 번만)
        anon_codes = [anon.get("/api/admin/support").status_code, anon.post(f"/api/admin/support/{target['id']}/handled").status_code]
        checks["일반_사용자_403·비로그인_401"] = normal == [403, 403] and anon_codes == [401, 401]
        admin_html = (WEB / "admin.html").read_text(encoding="utf-8")
        checks["관리자_화면에_문의_구역"] = all(s in admin_html for s in ("/api/admin/support", "처리함", 'id="support"')) and "TS.setPending(support" not in admin_html
    os.environ["ADMIN_EMAILS"] = saved_admins
    clean()
    checks["검수_행_정리"] = not rows()
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
