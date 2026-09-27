"""이용 신청과 관리자 승인 탭 검수 (2026-09-27 사용자 요청). 실제 메일은 보내지 않는다 (MAIL_FAKE_DIR). 모델을 부르지 않는다.

실행: uv run python -m tests.access.check_apply
- 승인 전 사용자: 신청서 제출(동의 필수·이유 10자 이상), 내 신청 상태 조회, 다시 내면 고쳐 씀. 승인 전에는 브리핑 API 403
- 관리자가 아니면: 신청 목록 API 403, /api/me에 신청 수 0, 승인 화면은 오늘 화면으로 돌려보냄
- 관리자: /api/me에 대기 신청 수, 신청 목록에 이름·하는 일·이유, 승인하면 목록에서 빠지고 브리핑 API 통과
- 승인된 뒤·차단된 뒤의 신청, 화면(신청 폼·승인 탭 관리자만·신청 글 이스케이프)
- 변경 이력(status_changes): 관리자 승인·차단은 누가·무엇에서 무엇으로 남고, 같은 상태로 누르면 안 남고, 초대 코드 가입은
  invite_code로 남고, 사용자 목록에 마지막 결정, 계정을 지우면 이력도 지워진다(계정 삭제가 막히지 않음)
- 실제 계정: ADMIN_EMAILS에 등록된 개발자 본인 계정은 users.is_admin도 켜져 있다 (읽기만, 주소는 코드에 적지 않는다)
검수용 사용자는 끝나면 지운다.
"""
import json
import os
import sys
from pathlib import Path

from sqlalchemy import delete, func, select

from tests.web import common

import db  # noqa: E402
from pipeline import deliver  # noqa: E402

APPLICANT = "apply-user@toolscout.test"
CODE_USER = "apply-code@toolscout.test"
CODE = "APPLYHIS"
ADMIN = "apply-admin@toolscout.test"
WEB = Path(__file__).resolve().parents[2] / "web"
FORM = {"name": "  홍길동 ", "job": "백엔드 개발자", "reason": "MCP 새 도구 소식을 매일 받아 보고 싶어요 <script>x</script>",
        "source": "GitHub", "agree": True}


def drop_admin(email: str) -> None:
    """검수 로그인은 개발 모드 때문에 주소를 ADMIN_EMAILS에 넣는다. 일반 사용자 역할은 다시 뺀다."""
    os.environ["ADMIN_EMAILS"] = ",".join(e for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip() and e.strip() != email)


OWNER_EMAILS = deliver.admin_emails()  # 검수 로그인이 테스트 주소를 더하기 전의 실제 관리자 목록


def main() -> int:
    common.cleanup_users("apply-")
    checks = {}
    try:
        with common.client() as user_c:
            admin_c = common.second_client()
            common.login(user_c, APPLICANT, approve=False)
            drop_admin(APPLICANT)
            common.login(admin_c, ADMIN, approve=True)

            checks["신청_전_상태_없음"] = user_c.get("/api/apply").json()["application"] is None
            checks["동의_안하면_400"] = user_c.post("/api/apply", json=FORM | {"agree": False}).status_code == 400
            checks["이유_10자_미만_422"] = user_c.post("/api/apply", json=FORM | {"reason": "짧아요"}).status_code == 422
            sent = user_c.post("/api/apply", json=FORM)
            mine = user_c.get("/api/apply").json()
            checks["신청_제출·앞뒤_공백_정리"] = sent.status_code == 200 and sent.json()["status"] == "pending" \
                and mine["application"]["name"] == "홍길동" and bool(mine["application"]["applied_at"])
            checks["다시_내면_고쳐씀"] = user_c.post("/api/apply", json=FORM | {"job": "데이터 엔지니어"}).status_code == 200 \
                and user_c.get("/api/apply").json()["application"]["job"] == "데이터 엔지니어"
            checks["승인_전에는_브리핑_403"] = user_c.get("/api/briefings/today").status_code == 403

            me_user = user_c.get("/api/me").json()
            checks["일반사용자는_신청목록_403"] = user_c.get("/api/admin/applications").status_code == 403
            checks["일반사용자_me에_신청수_0·관리자아님"] = me_user["is_admin"] is False and me_user["pending_applications"] == 0
            checks["일반사용자는_승인화면_못봄"] = user_c.get("/admin/invites", follow_redirects=False).status_code in (303, 307)

            me_admin = admin_c.get("/api/me").json()
            apps = admin_c.get("/api/admin/applications").json()["applications"]
            mine_row = next((a for a in apps if a["email"] == APPLICANT), None)
            checks["관리자_me에_대기_신청수"] = me_admin["is_admin"] is True and me_admin["pending_applications"] >= 1
            checks["관리자_신청목록에_내용"] = mine_row is not None and mine_row["job"] == "데이터 엔지니어" \
                and "<script>" in mine_row["reason"] and mine_row["source"] == "GitHub"
            approved = admin_c.post(f"/api/admin/users/{mine_row['id']}/status", json={"status": "approved"}) if mine_row else None
            after = admin_c.get("/api/admin/applications").json()["applications"]
            checks["승인하면_목록에서_빠지고_브리핑_통과"] = approved is not None and approved.status_code == 200 \
                and all(a["email"] != APPLICANT for a in after) and user_c.get("/api/briefings/today").status_code != 403
            checks["승인_뒤_신청은_이미_가입"] = user_c.post("/api/apply", json=FORM).json()["status"] == "approved"
            admin_c.post(f"/api/admin/users/{mine_row['id']}/status", json={"status": "blocked"})
            checks["차단되면_신청_403"] = user_c.post("/api/apply", json=FORM).status_code == 403
            admin_c.post(f"/api/admin/users/{mine_row['id']}/status", json={"status": "blocked"})  # 같은 상태로 한 번 더

            history = [h for h in admin_c.get("/api/admin/status-changes").json()["changes"] if h["email"] == APPLICANT]
            checks["이력_관리자_승인·차단_순서대로"] = [(h["old"], h["new"], h["via"], h["by"]) for h in reversed(history)] == [
                ("pending", "approved", "admin", ADMIN), ("approved", "blocked", "admin", ADMIN)]
            checks["이력_같은상태는_안남음"] = len(history) == 2
            listed = next(u for u in admin_c.get("/api/admin/users").json()["users"] if u["email"] == APPLICANT)
            checks["사용자목록에_마지막결정"] = (listed["last_change"] or {}).get("new") == "blocked"
            checks["로그인_안하면_이력_401·일반사용자는_403"] = common.second_client().get("/api/admin/status-changes").status_code == 401                 and user_c.get("/api/admin/status-changes").status_code == 403

            with db.session() as s:
                s.add(db.InviteCode(code=CODE, max_uses=1))
                s.commit()
            code_c = common.second_client()
            common.login(code_c, CODE_USER, approve=False)
            drop_admin(CODE_USER)
            redeemed = code_c.post("/api/invite/redeem", json={"code": CODE})
            coded = [h for h in admin_c.get("/api/admin/status-changes").json()["changes"] if h["email"] == CODE_USER]
            checks["이력_초대코드_가입은_invite_code"] = redeemed.status_code == 200 and [(h["old"], h["new"], h["via"], h["by"]) for h in coded] == [
                ("pending", "approved", "invite_code", None)]
    finally:
        user = common.user_id(APPLICANT)
        common.cleanup_users("apply-")
        with db.get_engine().begin() as conn:
            conn.execute(delete(db.InviteCode).where(db.InviteCode.code == CODE))
            left = conn.execute(select(func.count()).select_from(db.StatusChange).where(db.StatusChange.user_id == user)).scalar() if user else 0
        checks["계정_지우면_이력도_지워짐"] = left == 0

    invite, admin, app = ((WEB / n).read_text(encoding="utf-8") for n in ("invite.html", "admin.html", "app.js"))
    checks["화면_신청폼·동의·초대코드_함께"] = all(k in invite for k in ('id="apply-form"', 'id="agree"', 'id="invite-form"', "/api/apply"))
    checks["화면_승인탭은_관리자만"] = "me && me.is_admin ?" in app and '"/admin/invites"' in app
    checks["화면_신청글_이스케이프"] = all(f"TS.esc(a.{k})" in admin for k in ("name", "job", "reason", "source"))

    owners = [e.lower() for e in OWNER_EMAILS if not e.lower().endswith(common.TEST_DOMAIN)]
    with db.get_engine().connect() as conn:
        flags = conn.execute(select(db.User.is_admin).where(db.User.email.in_(owners))).scalars().all()
    checks["실제계정_슈퍼관리자(설정·DB)"] = bool(owners) and bool(flags) and all(flags)

    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
