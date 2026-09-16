"""데모 프로필 하루 실행 1명분 (화면 확인용)."""
import asyncio, json
from sqlmodel import select
import db
from pipeline import run_daily
from agent import tracing

with db.session() as s:
    demo_id = s.exec(select(db.User.id).where(db.User.is_demo == True)).first()  # noqa: E712
print("데모 사용자", demo_id)
try:
    result = asyncio.run(run_daily.run(user_ids=[demo_id], limit=40))
finally:
    tracing.flush()
print(json.dumps({k: v for k, v in result.items() if k in ("date", "users", "cards", "stats", "seconds", "trace_id", "status")},
                 ensure_ascii=False, default=str)[:900])
