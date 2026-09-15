"""SQLModel 데이터 표 9개 (계획안 9.5).

DB는 Supabase(Postgres) 하나로 간다. 연결 문자열은 .env의 DATABASE_URL에만 둔다.
드라이버는 psycopg 3. Supabase에서 복사한 postgresql:// 문자열을 그대로 넣으면 여기서 변환한다.
연결은 Session pooler(5432) 기준이다.
기사 본문은 저장하지 않는다. items에는 요약, 링크, 메타데이터만 둔다 (작업 규칙 9).
"""
import logging
import os
from contextlib import contextmanager
from datetime import date as Date, datetime, timezone
from functools import lru_cache
from typing import Any, Iterator
from urllib.parse import parse_qsl, unquote, urlsplit

from sqlalchemy import CheckConstraint, Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import URL, Engine
from sqlmodel import Field, Session, SQLModel, create_engine

import config  # noqa: F401  .env를 os.environ에 채운다

log = logging.getLogger("toolscout.db")

DRIVER = "postgresql+psycopg"
SESSION_POOLER_PORT = 5432
TRANSACTION_POOLER_PORT = 6543


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jsonb(nullable: bool = False) -> Column:
    return Column(JSONB, nullable=nullable)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    kakao_id: str | None = Field(default=None, unique=True, index=True)
    email: str | None = Field(default=None, unique=True, index=True)
    role: str  # 직군 (프로필 필수 칸)
    profile_tools_tags: list[str] = Field(default_factory=list, sa_column=_jsonb())
    profile_free_text: str | None = None
    channel: str = "email"
    class_code: str | None = Field(default=None, index=True)
    is_admin: bool = False
    is_test: bool = Field(default=False, index=True)  # 개발 모드 가짜 프로필. 무료 모델에는 이 사용자만 보낸다
    mcp_key_hash: str | None = Field(default=None, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


class Weight(SQLModel, table=True):
    __tablename__ = "weights"
    __table_args__ = (CheckConstraint("weight BETWEEN -5 AND 5", name="ck_weights_range"),)

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    topic: str = Field(primary_key=True)  # 주제 10개 고정 (목록은 계획안 확정 후)
    weight: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class Item(SQLModel, table=True):
    __tablename__ = "items"
    __table_args__ = (CheckConstraint("type IN ('news', 'mcp', 'skill')", name="ck_items_type"),)

    id: int | None = Field(default=None, primary_key=True)
    date: Date = Field(index=True)
    type: str
    topic: str | None = None
    title: str
    url: str = Field(unique=True, index=True)
    summary_ko: str | None = None
    source: str
    source_tier: int | None = None
    version: str | None = None
    stars: int | None = None
    stars_checked_at: datetime | None = None  # GitHub 별 수 조회 시각. 24시간 캐시 기준
    deadline_at: datetime | None = None


class Seen(SQLModel, table=True):
    __tablename__ = "seen"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    item_id: int = Field(foreign_key="items.id", primary_key=True)
    shown_at: datetime = Field(default_factory=utcnow)


class Probe(SQLModel, table=True):
    __tablename__ = "probes"

    item_id: int = Field(foreign_key="items.id", primary_key=True)
    install: str | None = None  # 성공/실패/해당없음
    run: str | None = None
    tools_list: str | None = None
    auth_required: bool | None = None
    duration_ms: int | None = None
    requirements: list[str] = Field(default_factory=list, sa_column=_jsonb())
    log: str | None = None
    probed_at: datetime = Field(default_factory=utcnow)


class SkillReview(SQLModel, table=True):
    __tablename__ = "skill_reviews"
    __table_args__ = (CheckConstraint("risk_signal IN ('ok', 'caution', 'unverified')", name="ck_skill_reviews_risk"),)

    item_id: int = Field(foreign_key="items.id", primary_key=True)
    purpose: str | None = None
    trigger: str | None = None
    steps_summary: str | None = None
    risk_signal: str = "unverified"
    risk_quote: str | None = None
    regex_hits: list[str] = Field(default_factory=list, sa_column=_jsonb())
    completeness: str | None = None


class Briefing(SQLModel, table=True):
    """사용자·날짜별 카드 행. 카드가 0건인 날은 item_id 없이 empty_reason만 있는 행 하나를 남긴다 (rank 0)."""
    __tablename__ = "briefings"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "item_id", name="uq_briefings_user_date_item", postgresql_nulls_not_distinct=True),
        CheckConstraint("(item_id IS NOT NULL AND card_json IS NOT NULL) OR (item_id IS NULL AND empty_reason IS NOT NULL)",
                        name="ck_briefings_card_or_empty"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    date: Date = Field(index=True)
    item_id: int | None = Field(default=None, foreign_key="items.id")
    rank: int
    card_json: dict[str, Any] | None = Field(default=None, sa_column=_jsonb(nullable=True))
    empty_reason: str | None = None
    # trace_id 없는 카드는 만들지 않는다 (작업 규칙 10). 빈 행도 그날 실행의 trace_id를 남긴다
    trace_id: str = Field(sa_column=Column(String, nullable=False))
    sent_at: datetime | None = None


class Feedback(SQLModel, table=True):
    __tablename__ = "feedback"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    item_id: int = Field(foreign_key="items.id")
    action: str  # 관심없음 / 써봤음 / 이상함
    reason: str | None = None
    memo: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Question(SQLModel, table=True):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("user_id", "session_date", "turn_no", name="uq_questions_turn"),
        CheckConstraint("gate IN ('in', 'out', 'unclear')", name="ck_questions_gate"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    session_date: Date
    turn_no: int
    question: str
    gate: str
    answer: str | None = None
    sources_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=_jsonb())
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


TABLES = ["users", "weights", "seen", "items", "probes", "skill_reviews", "briefings", "feedback", "questions"]


def database_url() -> URL:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("DATABASE_URL이 비어 있다. .env에 Supabase Postgres 연결 문자열을 넣는다.")
    return normalize_database_url(raw)


def normalize_database_url(raw: str) -> URL:
    """Supabase 연결 문자열을 psycopg용 SQLAlchemy URL로 바꾼다. 오류 문구에 값을 넣지 않는다.

    - postgres://, postgresql:// → postgresql+psycopg://
    - 비밀번호의 @ : / # ? 같은 특수문자는 인코딩했든 안 했든 처리한다 (마지막 @를 호스트 경계로 본다)
    """
    scheme, sep, rest = raw.partition("://")
    if not sep or scheme not in ("postgres", "postgresql", DRIVER):
        raise ValueError("DATABASE_URL은 postgresql://로 시작해야 한다")
    userinfo, at, hostpart = rest.rpartition("@")
    if not at:
        raise ValueError("DATABASE_URL에 사용자·비밀번호 부분이 없다")
    username, _, password = userinfo.partition(":")
    parts = urlsplit("//" + hostpart)
    try:
        port = parts.port
    except ValueError:
        raise ValueError("DATABASE_URL의 포트가 숫자가 아니다") from None
    if port == TRANSACTION_POOLER_PORT:
        log.warning("DATABASE_URL이 Transaction pooler(6543)다. Session pooler(5432) 연결 문자열을 권장한다")
    return URL.create(DRIVER, username=unquote(username) or None, password=unquote(password) or None,
                      host=parts.hostname, port=port, database=unquote(parts.path.lstrip("/")) or None,
                      query=dict(parse_qsl(parts.query)))


@lru_cache
def get_engine(url: URL | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


# 표를 만든 뒤에 추가한 칸. create_all은 이미 있는 표에 칸을 더하지 않으므로 없을 때만 추가한다
ADDED_COLUMNS = [("items", "stars_checked_at", "TIMESTAMP WITHOUT TIME ZONE"), ("briefings", "empty_reason", "VARCHAR")]

# 이미 만든 briefings 표를 카드 0건 행을 담을 수 있게 바꾼다 (2026-09-14). 데이터는 지우지 않고, 여러 번 돌려도 같다
# (user_id, date, item_id) 복합 기본키 → id 기본키 + 같은 조합 유일(NULL도 같은 값으로 봄)
BRIEFINGS_MIGRATION = [
    "ALTER TABLE briefings ADD COLUMN IF NOT EXISTS id INTEGER GENERATED BY DEFAULT AS IDENTITY",
    """DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                 WHERE c.conrelid = 'briefings'::regclass AND c.contype = 'p' AND a.attname = 'item_id') THEN
        ALTER TABLE briefings DROP CONSTRAINT briefings_pkey;
        ALTER TABLE briefings ADD CONSTRAINT briefings_pkey PRIMARY KEY (id);
      END IF;
    END $$""",
    "ALTER TABLE briefings ALTER COLUMN item_id DROP NOT NULL",
    "ALTER TABLE briefings ALTER COLUMN card_json DROP NOT NULL",
    """DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_briefings_user_date_item') THEN
        ALTER TABLE briefings ADD CONSTRAINT uq_briefings_user_date_item UNIQUE NULLS NOT DISTINCT (user_id, date, item_id);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_briefings_card_or_empty') THEN
        ALTER TABLE briefings ADD CONSTRAINT ck_briefings_card_or_empty CHECK
          ((item_id IS NOT NULL AND card_json IS NOT NULL) OR (item_id IS NULL AND empty_reason IS NOT NULL));
      END IF;
    END $$""",
    "CREATE INDEX IF NOT EXISTS ix_briefings_user_id ON briefings (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_briefings_date ON briefings (date)",
]


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        for table, column, sql_type in ADDED_COLUMNS:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}")
        for statement in BRIEFINGS_MIGRATION:
            connection.exec_driver_sql(statement)


# 개발 모드 프로필 (is_test). 주소는 .test 도메인이고, 개발 모드 발송은 받는 사람을 ADMIN_EMAILS로 바꾼다
# - A·B: 계획안 부록 B 검수 기준의 가짜 프로필 (두 브리핑이 다르게 나오는지 비교)
# - C: 개발자 본인 관심사를 공개돼도 되는 수준으로 적은 프로필. 무료 모델에 들어간다 (2026-09-15 사용자 승인)
TEST_USERS = [
    {"email": "test-backend@toolscout.test", "role": "자바 백엔드 개발자",
     "profile_tools_tags": ["java", "spring", "n8n"], "profile_free_text": "n8n으로 사내 AI 브리핑 봇을 만든다"},
    {"email": "test-marketer@toolscout.test", "role": "마케터",
     "profile_tools_tags": ["notion"], "profile_free_text": "노션으로 캠페인 기록과 콘텐츠 일정을 관리한다"},
    {"email": "test-ai-learner@toolscout.test", "role": "AI 에이전트를 공부하는 개발자",
     "profile_tools_tags": ["python", "claude code", "mcp"],
     "profile_free_text": "AI 에이전트를 공부하고 있어 새 모델, 에이전트 프레임워크, MCP 도구 소식이 궁금하다"},
]


def seed_test_users(engine: Engine | None = None) -> list[int]:
    """개발 모드 프로필을 이메일 기준으로 한 번만 만든다. 반환: 사용자 id 목록 (A, B, C 순)."""
    from sqlmodel import select

    ids = []
    with Session(engine or get_engine()) as s:
        for profile in TEST_USERS:
            user = s.exec(select(User).where(User.email == profile["email"])).first()
            if user is None:
                user = User(**profile, is_test=True)
                s.add(user)
            user.is_test = True
            s.commit()
            s.refresh(user)
            ids.append(user.id)
    return ids


@contextmanager
def session(engine: Engine | None = None) -> Iterator[Session]:
    with Session(engine or get_engine()) as s:
        yield s
