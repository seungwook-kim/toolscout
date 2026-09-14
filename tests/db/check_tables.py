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
from sqlmodel import SQLModel

ROOT = Path(__file__).resolve().parents[2]

import config  # noqa: E402
import db  # noqa: E402

# 계획안 9.5 주요 칸
PLAN_COLUMNS = {
    "users": "id kakao_id email role profile_tools_tags profile_free_text channel class_code is_admin mcp_key_hash created_at",
    "weights": "user_id topic weight updated_at",
    "seen": "user_id item_id shown_at",
    "items": "id date type topic title url summary_ko source source_tier version stars deadline_at",
    "probes": "item_id install run tools_list auth_required duration_ms requirements log probed_at",
    "skill_reviews": "item_id purpose trigger steps_summary risk_signal risk_quote regex_hits completeness",
    "briefings": "user_id date item_id rank card_json trace_id sent_at",
    "feedback": "user_id item_id action reason memo created_at",
    "questions": "user_id session_date turn_no question gate answer sources_json trace_id created_at",
}
CHECKS = {"ck_weights_range", "ck_items_type", "ck_skill_reviews_risk", "ck_questions_gate"}


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


def live_create() -> str:
    if not os.environ.get("DATABASE_URL"):
        return "미실행(Supabase 미설정)"
    try:
        engine = db.get_engine()
        db.init_db(engine)
        names = set(inspect(engine).get_table_names())
        return "성공" if set(db.TABLES) <= names else f"누락 {sorted(set(db.TABLES) - names)}"
    except Exception as exc:
        return f"실패 {type(exc).__name__}: {config.redact(str(exc))[:200]}"


def main() -> int:
    tables = SQLModel.metadata.tables
    columns = {name: set(tables[name].columns.keys()) for name in db.TABLES if name in tables}
    missing = {n: sorted(set(c.split()) - columns.get(n, set())) for n, c in PLAN_COLUMNS.items()}
    constraints = {c.name for t in tables.values() for c in t.constraints if isinstance(c, CheckConstraint)}
    ddl = ddl_compiles()
    json_cols = [f"{t}.{c.name}" for t in db.TABLES for c in tables[t].columns if isinstance(c.type, postgresql.JSONB)]
    checks = {
        "표_9개": set(tables) == set(db.TABLES),
        "계획안_칸_모두_있음": not any(missing.values()),
        "postgres_DDL_컴파일": all(v is True for v in ddl.values()),
        "JSON_칸_5개는_JSONB": len(json_cols) == 5,
        "briefings_trace_id_NOT_NULL": tables["briefings"].c.trace_id.nullable is False,
        "check_제약_4개": CHECKS <= constraints,
        "sqlite_흔적_없음": "sqlite" not in (ROOT / "db.py").read_text(encoding="utf-8").lower(),
        "DATABASE_URL_없으면_명확한_에러": missing_url_raises(),
        **url_checks(),
    }
    report = {"checks": checks, "missing_columns": missing, "json_columns": json_cols,
              "live_create": live_create(), "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
