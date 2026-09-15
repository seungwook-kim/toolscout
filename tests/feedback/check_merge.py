"""주간 기억 합치기 검수 (계획안 5장 기억 설계 표, 부록 C 5, 2026-09-15 사용자 결정 "직군 프리셋 값으로"). 모델 호출 없음.

실행: uv run python -m tests.feedback.check_merge
검수용 사용자(직군 개발자)와 항목을 넣고 끝나면 지운다.
- 40일 전 관심없음 3회로 1 → -2가 된 가격 주제는 직군 프리셋 1로 돌아가고, 그 피드백 기록은 남되 weight_delta는 0
- 최근 써봤음으로 3 → 4가 된 에이전트 주제는 그대로 / 오래된 관심없음이 있어도 최근 이상함을 눌렀으면 그대로
- 설정에서 직접 5로 올린 코딩 도구 주제는 그대로 / 피드백 뒤 설정에서 값을 고친 주제는 고친 값이 기준(다시 빼지 않음)
- 두 번 돌려도 같다 / 되돌린 뒤 옛 버튼을 다시 눌러 취소해도 가중치가 또 바뀌지 않는다
"""
import json
import sys
from datetime import date, timedelta

from tests.web import common

from sqlalchemy import delete, insert, select, update  # noqa: E402

import db  # noqa: E402
import memory  # noqa: E402

EMAIL = "web-merge@toolscout.test"
HOST = "https://example.test/merge/"
DAY = date(2000, 1, 10)


def cleanup() -> None:
    common.cleanup_users("web-merge")
    with db.get_engine().begin() as c:
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def weights(uid: int) -> dict:
    with db.get_engine().connect() as c:
        return dict(c.execute(select(db.Weight.topic, db.Weight.weight).where(db.Weight.user_id == uid)).all())


def main() -> int:
    cleanup()
    try:
        with db.get_engine().begin() as c:
            uid = c.execute(insert(db.User).values(email=EMAIL, role="개발자", is_test=True, profile_tools_tags=[], notify_time="08:00",
                                                   channel="email").returning(db.User.id)).scalar_one()
        preset = memory.ROLE_PRESETS["개발자"]
        memory.save_profile(uid, role="개발자", tools_tags=[], free_text=None, weights=preset | {"coding_tools": 5})
        specs = [("pricing", 3), ("agent_framework", 1), ("data_rag", 2), ("industry", 1), ("model_release", 1)]
        items: dict[str, list[int]] = {}
        with db.get_engine().begin() as c:
            for topic, count in specs:
                for n in range(count):
                    item_id = c.execute(insert(db.Item).values(date=DAY, type="news", topic=topic, title=f"{topic} {n}",
                                                               url=f"{HOST}{topic}/{n}", source="test").returning(db.Item.id)).scalar_one()
                    c.execute(insert(db.Briefing).values(user_id=uid, date=DAY, item_id=item_id, rank=len(items) + n + 1, trace_id="t",
                                                         card_json={"item_id": item_id, "type": "news", "title": topic}))
                    items.setdefault(topic, []).append(item_id)
        old = []
        old += [memory.apply_feedback(uid, i, "관심없음")["feedback_id"] for i in items["pricing"]]
        memory.apply_feedback(uid, items["agent_framework"][0], "써봤음")
        old.append(memory.apply_feedback(uid, items["data_rag"][0], "관심없음")["feedback_id"])
        memory.apply_feedback(uid, items["data_rag"][1], "이상함")  # 최근 반응
        old.append(memory.apply_feedback(uid, items["industry"][0], "관심없음")["feedback_id"])
        old.append(memory.apply_feedback(uid, items["model_release"][0], "이상함")["feedback_id"])
        with db.get_engine().begin() as c:
            c.execute(update(db.Feedback).where(db.Feedback.id.in_(old)).values(created_at=db.utcnow() - timedelta(days=40)))
        before = weights(uid)
        memory.save_profile(uid, role="개발자", tools_tags=[], free_text=None, weights=before | {"industry": 2})  # 설정에서 산업만 고침
        first = memory.merge_weights(user_ids=[uid])
        after = weights(uid)
        with db.get_engine().connect() as c:
            pricing_rows = c.execute(select(db.Feedback.weight_delta).where(db.Feedback.user_id == uid,
                                                                            db.Feedback.item_id.in_(items["pricing"]))).all()
        second = memory.merge_weights(user_ids=[uid])
        after_second = weights(uid)
        cancel = memory.apply_feedback(uid, items["pricing"][0], "관심없음")
        after_cancel = weights(uid)
    finally:
        cleanup()
    mine = [r for r in first["reverted"] if r["user_id"] == uid]
    checks = {
        "피드백으로_바뀐_값_확인": before["pricing"] == -2 and before["agent_framework"] == 4 and before["data_rag"] == 1,
        "40일_무반응_가격은_직군프리셋으로": after["pricing"] == preset["pricing"] == 1
        and mine == [{"user_id": uid, "topic": "pricing", "before": -2, "after": 1}],
        "되돌린_피드백은_기록남고_delta_0": len(pricing_rows) == 3 and all(r[0] == 0 for r in pricing_rows),
        "최근_써봤음_주제는_그대로": after["agent_framework"] == 4,
        "최근_이상함을_눌렀으면_그대로": after["data_rag"] == 1,
        "설정에서_올린_값은_그대로": after["coding_tools"] == 5,
        "피드백뒤_설정에서_고친_값이_기준": after["industry"] == 2,
        "delta0_이상함만_있으면_변화없음": after["model_release"] == preset["model_release"],
        "두번_돌려도_같음": not [r for r in second["reverted"] if r["user_id"] == uid] and after_second == after,
        "되돌린뒤_옛버튼_취소해도_안바뀜": cancel["status"] == "cancelled" and after_cancel["pricing"] == 1,
    }
    report = {"checks": checks, "before": before, "after": after, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
