"""SQLModel 데이터 표 9개 (계획안 9.5).

DB는 Supabase(Postgres) 하나로 간다. 연결 문자열은 .env의 DATABASE_URL에만 둔다.
Postgres 드라이버 설치와 Supabase 프로젝트 설정은 뒤에서 한다.
기사 본문은 저장하지 않는다. items에는 요약, 링크, 메타데이터만 둔다 (작업 규칙 9).
"""
import os
from contextlib import contextmanager
from datetime import date as Date, datetime, timezone
from functools import lru_cache
from typing import Any, Iterator

from sqlalchemy import CheckConstraint, Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine


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
    __tablename__ = "briefings"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    date: Date = Field(primary_key=True)
    item_id: int = Field(foreign_key="items.id", primary_key=True)
    rank: int
    card_json: dict[str, Any] = Field(sa_column=_jsonb())
    # trace_id 없는 카드는 만들지 않는다 (작업 규칙 10)
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


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL이 비어 있다. .env에 Supabase Postgres 연결 문자열을 넣는다.")
    return url


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def init_db(engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(engine or get_engine())


@contextmanager
def session(engine: Engine | None = None) -> Iterator[Session]:
    with Session(engine or get_engine()) as s:
        yield s
