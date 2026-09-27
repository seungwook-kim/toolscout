"""db.py 검수 (착수 프롬프트 0단계 7번, Supabase 전용으로 조정).

실행: uv run python -m tests.db.check_tables
연결 없이 도는 검사(표 9개, 칸, Postgres DDL, 제약)와 DATABASE_URL이 있을 때만 도는 실제 생성으로 나뉜다.
"""
import json
import os
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from sqlmodel import SQLModel, select

ROOT = Path(__file__).resolve().parents[2]

import config  # noqa: E402
import db  # noqa: E402

# 계획안 9.5 주요 칸
PLAN_COLUMNS = {
    "users": "id kakao_id email role profile_tools_tags profile_free_text channel class_code is_admin mcp_key_hash created_at",
    "weights": "user_id topic weight updated_at",
    "seen": "user_id item_id shown_at",
    "items": "id date type topic title url summary_ko description source source_tier version stars deadline_at",
    "probes": "item_id install run tools_list auth_required duration_ms requirements log probed_at",
    "skill_reviews": "item_id purpose trigger steps_summary risk_signal risk_quote regex_hits completeness",
    "briefings": "user_id date item_id rank card_json trace_id sent_at",
    "feedback": "user_id item_id action reason memo created_at",
    "questions": "user_id session_date turn_no question gate answer sources_json trace_id created_at",
    "used_tokens": "token_hash purpose used_at expires_at",
    "invite_codes": "code max_uses used expires_at created_by created_at",  # 초대제 (2026-09-16)
    "status_changes": "user_id old_status new_status changed_by via changed_at",  # 가입 상태 변경 이력 (2026-09-27)
}
CHECKS = {"ck_weights_range", "ck_items_type", "ck_skill_reviews_risk", "ck_questions_gate", "ck_users_status", "ck_status_changes_via"}


def ddl_compiles() -> dict:
    out = {}
    for table in SQLModel.metadata.sorted_tables:
        try:
            CreateTable(table).compile(dialect=postgresql.dialect())
            out[table.name] = True
        except Exception as exc:
            out[table.name] = f"{type(exc).__name__}: {exc}"
    return out


def missing_url_raises() -> bool:
    saved = os.environ.pop("DATABASE_URL", None)
    try:
        db.database_url()
        return False
    except RuntimeError:
        return True
    finally:
        if saved is not None:
            os.environ["DATABASE_URL"] = saved


def url_checks() -> dict:
    """가짜 연결 문자열로 변환 규칙을 확인한다. 실제 DATABASE_URL은 쓰지 않는다."""
    fake_password = "p@ss:w/rd#1?"
    raw = f"postgresql://postgres.fakeref:{fake_password}@aws-0-fake.pooler.supabase.com:5432/postgres"
    url = db.normalize_database_url(raw)
    encoded = db.normalize_database_url("postgres://u:p%40ss@h.example.com:5432/db?sslmode=require")
    errors = []
    for bad in (f"DATABASE_URL=postgresql://u:{fake_password}@h:5432/db", "mysql://u:x@h/db"):
        try:
            db.normalize_database_url(bad)
            errors.append("통과해버림")
        except ValueError as exc:
            errors.append(str(exc))
    return {
        "드라이버_psycopg로_변환": url.drivername == "postgresql+psycopg" and encoded.drivername == "postgresql+psycopg",
        "특수문자_비밀번호_그대로": url.password == fake_password and url.host == "aws-0-fake.pooler.supabase.com"
        and url.port == 5432 and url.username == "postgres.fakeref" and url.database == "postgres",
        "인코딩된_비밀번호·쿼리": encoded.password == "p@ss" and encoded.query.get("sslmode") == "require",
        "잘못된_형식은_값_없이_에러": len(errors) == 2 and "통과해버림" not in errors
        and not any(fake_password in e for e in errors),
    }


def live_create() -> dict:
    """Supabase에 표를 만들고 개발 프로필 A·B·C와 데모 프로필을 넣는다. 이미 있는 표에 칸이 빠졌는지도 본다."""
    if not os.environ.get("DATABASE_URL"):
        return {"status": "미실행(DATABASE_URL 비어있음)", "ok": False}
    try:
        engine = db.get_engine()
        db.init_db(engine)
        inspector = inspect(engine)
        names = set(inspector.get_table_names())
        user_columns = {c["name"] for c in inspector.get_columns("users")} if "users" in names else set()
        item_columns = {c["name"] for c in inspector.get_columns("items")} if "items" in names else set()
        briefing_columns = {c["name"]: c for c in inspector.get_columns("briefings")}
        briefing_pk = inspector.get_pk_constraint("briefings")["constrained_columns"]
        briefing_unique = {u["name"] for u in inspector.get_unique_constraints("briefings")}
        test_ids = db.seed_test_users(engine)
        with db.session(engine) as s:
            test_users = s.exec(select(db.User).where(db.User.is_test == True)).all()  # noqa: E712
        result = {
            "status": "성공",
            "tables_created": sorted(set(db.TABLES) & names),
            "missing_tables": sorted(set(db.TABLES) - names),
            "users_is_test_column": "is_test" in user_columns,
            "users_초대제_칸": {"status", "invite_code_used", "is_demo"} <= user_columns,
            "items_stars_checked_at_column": "stars_checked_at" in item_columns,
            "briefings_empty_row_ready": ("empty_reason" in briefing_columns and briefing_pk == ["id"]
                                          and briefing_columns["item_id"]["nullable"]
                                          and "uq_briefings_user_date_item" in briefing_unique),
            "test_user_ids": test_ids,
            "test_users": [{"id": u.id, "role": u.role, "tools": u.profile_tools_tags} for u in test_users],
        }
        result["demo_user_id"] = db.seed_demo_user(engine)
        result["ok"] = (not result["missing_tables"] and result["users_is_test_column"] and result["users_초대제_칸"]
                        and result["items_stars_checked_at_column"] and result["briefings_empty_row_ready"]
                        and len(test_users) >= 2)
        return result
    except Exception as exc:
        return {"status": f"실패 {type(exc).__name__}: {config.redact(str(exc))[:200]}", "ok": False}


def main() -> int:
    tables = SQLModel.metadata.tables
    columns = {name: set(tables[name].columns.keys()) for name in db.TABLES if name in tables}
    missing = {n: sorted(set(c.split()) - columns.get(n, set())) for n, c in PLAN_COLUMNS.items()}
    constraints = {c.name for t in tables.values() for c in t.constraints if isinstance(c, CheckConstraint)}
    ddl = ddl_compiles()
    json_cols = [f"{t}.{c.name}" for t in db.TABLES for c in tables[t].columns if isinstance(c.type, postgresql.JSONB)]
    checks = {
        "표_13개(used_tokens·verify_requests·invite_codes·status_changes_포함)": set(tables) == set(db.TABLES) and len(db.TABLES) == 13,
        "계획안_칸_모두_있음": not any(missing.values()),
        "postgres_DDL_컴파일": all(v is True for v in ddl.values()),
        "JSON_칸_10개는_JSONB(run_stats·probes.tools·stages·verify_requests.install·users.application 포함)": len(json_cols) == 10,
        "briefings_trace_id_NOT_NULL": tables["briefings"].c.trace_id.nullable is False,
        "check_제약_6개": CHECKS <= constraints,
        "sqlite_흔적_없음": "sqlite" not in (ROOT / "db.py").read_text(encoding="utf-8").lower(),
        "DATABASE_URL_없으면_명확한_에러": missing_url_raises(),
        "users_is_test_칸": "is_test" in columns["users"],
        "briefings_카드0건_행(empty_reason·item_id_NULL허용)": "empty_reason" in columns["briefings"]
        and tables["briefings"].c.item_id.nullable is True,
        "개발_프로필_A·B·C_정의": [u["role"] for u in db.TEST_USERS] == ["자바 백엔드 개발자", "마케터", "AI 에이전트를 공부하는 개발자"],
        **url_checks(),
    }
    live = live_create()
    checks["supabase_표9개·가짜프로필2개"] = live["ok"]
    report = {"checks": checks, "missing_columns": missing, "json_columns": json_cols,
              "live_create": live, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
