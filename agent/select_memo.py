"""뉴스 선별 판정 재사용 (2026-10-16 사용자 결정 "전부 다 진행해줘"의 C).

수집 창이 48시간이라 전날 판정한 뉴스가 다음 날 다시 후보로 들어온다. 10/8~10/11 골든셋에서 잘못 통과한 85건 중
약 10건이 같은 기사가 이틀 넘게 다시 판정돼 다시 통과한 것이었다. 오늘·어제 판정이 있는 뉴스는 모델에 보내지 않고
그 판정을 쓴다(같은 날 다시 도는 재시도·지금 만들기도 같은 판정). 도구(MCP·스킬)는 버전이 바뀌므로 매번 판정한다.
골든셋(tests/golden/fetch_select.py)은 트레이스의 모델 판정만 꺼내므로 재사용한 뉴스는 그날 채점에서 빠진다(처음 본 기사만 채점).
키는 정리된 링크(pipeline/normalize). DB에는 판정·주제·중요도·근거 한 줄과 제목만 두고 기사 본문·요약은 두지 않는다(작업 규칙 9).
"""
from datetime import date, timedelta

from sqlmodel import col, delete, select

import db

REUSE_DAYS = 1  # 오늘과 어제 (수집 창 48시간)
KEEP_DAYS = 7


def load(today: date, items: list[dict]) -> dict[str, dict]:
    """반환: {링크: {ai_related, worth_today, topic, importance, reason}}. 링크마다 가장 최근 날짜의 판정."""
    urls = sorted({i["url"] for i in items if i.get("type") == "news" and i.get("url")})
    if not urls:
        return {}
    with db.session() as s:
        rows = s.exec(select(db.SelectMemo).where(col(db.SelectMemo.url).in_(urls), db.SelectMemo.day >= today - timedelta(days=REUSE_DAYS),
                                                  db.SelectMemo.day <= today).order_by(db.SelectMemo.day)).all()
    return {r.url: {"ai_related": r.ai_related, "worth_today": r.worth_today, "topic": r.topic, "importance": r.importance,
                    "reason": r.reason} for r in rows}


def save(today: date, judged: list[dict]) -> int:
    """오늘 모델이 판정한 뉴스를 남기고 KEEP_DAYS 지난 행을 지운다. 반환: 저장한 행 수."""
    rows = {j["url"]: j for j in judged if j.get("url")}
    with db.session() as s:
        s.exec(delete(db.SelectMemo).where(db.SelectMemo.day < today - timedelta(days=KEEP_DAYS)))
        for url, j in rows.items():
            s.merge(db.SelectMemo(url=url, day=today, title=j["title"][:300], ai_related=j["ai_related"], worth_today=j["worth_today"],
                                  topic=j["topic"], importance=j["importance"], reason=j["reason"][:200]))
        s.commit()
    return len(rows)
