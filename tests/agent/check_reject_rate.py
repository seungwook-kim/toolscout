"""해설가 반려율 검수 (2026-09-21). 실제 모델을 부른다 (개발 모드 무료·로컬).

왜: 큐레이터가 프로필을 보고 고른 항목을 해설가가 다시 심사하는데 기준이 더 좁았다.
자유 한 줄에 적힌 지금 하는 일에 그대로 쓸 수 있는지로만 보아, 백엔드 프로필 7건 중 6건이 반려됐고
마케터는 9월 18·19일에 후보 8건이 모두 반려돼 브리핑이 비었다.

실행: uv run python -m tests.agent.check_reject_rate (앱이 8000 포트에 떠 있어야 한다. fetch_article을 실제로 쓴다)
실제로 반려됐던 항목을 그대로 다시 넣어 반려율과 관련도를 잰다. 프롬프트가 널널해져 아무거나 통과하면
안 되므로, 프로필과 정말 무관한 대조 항목은 계속 반려되는지도 같이 본다.
"""
import asyncio
import json
import os
import sys

import memory
from agent import explainer, schemas

MCP_URL = os.environ.get("TOOLSCOUT_MCP_URL", "http://127.0.0.1:8000/mcp")

# 2026-09-21 daily_report.json에서 실제로 반려됐던 항목 (자바 백엔드 프로필)
WAS_REJECTED = [
    {"title": "앤트로픽 '페이블 5.1', 370년 미해결 난제 암호 44분 만에 풀었다",
     "url": "https://www.aitimes.com/news/articleView.html?idxno=215301", "type": "news", "source": "aitimes",
     "summary": "앤트로픽이 페이블 5.1로 370년간 풀리지 않던 암호를 44분 만에 해독했다고 밝혔다.",
     "why": "새 모델의 실제 추론 성능을 보여 주는 사례", "topic": "model_release", "rank": 1},
    {"title": "MS, '인본주의적 AI 행동 강령' 공개...\"AI는 인간에게 종속돼야\"",
     "url": "https://www.aitimes.com/news/articleView.html?idxno=215268", "type": "news", "source": "aitimes",
     "summary": "마이크로소프트가 AI 개발·운영 원칙을 담은 행동 강령을 공개했다.",
     "why": "에이전트를 만드는 사람이 알아야 할 정책 흐름", "topic": "safety_policy", "rank": 2},
    {"title": "“AI 에이전트가 상호 거래·정산까지”...카카오페이 자율결제 실증 완료",
     "url": "https://www.aitimes.com/news/articleView.html?idxno=215311", "type": "news", "source": "aitimes",
     "summary": "카카오페이가 AI 에이전트끼리 거래하고 정산하는 자율결제 실증을 마쳤다.",
     "why": "에이전트가 실제 업무를 끝까지 수행하는 사례", "topic": "agent_framework", "rank": 3},
]

# 프로필과 정말 무관한 대조군. 이것까지 통과하면 프롬프트가 너무 널널해진 것이다
SHOULD_REJECT = [
    {"title": "오늘의 점심 메뉴 추천 이벤트 안내", "url": "https://example.test/lunch", "type": "news",
     "source": "test", "summary": "구내식당 점심 메뉴 추천 이벤트를 연다.", "why": "검수용 대조 항목",
     "topic": "industry", "rank": 4},
]


async def main() -> int:
    user_id = memory.test_user_ids()[0]  # 자바 백엔드 프로필
    mem = memory.read(user_id)
    plan = {"user_id": user_id, "news": WAS_REJECTED + SHOULD_REJECT, "tools": []}
    result = await explainer.run([plan], [mem], MCP_URL)
    user = result["users"][0]
    cards = {c["title"]: c for c in user["cards"]}
    rejected = {r["title"] for r in user["rejected"]}

    revived = [i["title"] for i in WAS_REJECTED if i["title"] in cards]
    control_rejected = SHOULD_REJECT[0]["title"] in rejected
    relevances = [cards[t]["relevance"] for t in revived if cards[t].get("relevance") is not None]

    print(f"\n전에 반려됐던 {len(WAS_REJECTED)}건 중 살아난 것: {len(revived)}건")
    for t in revived:
        c = cards[t]
        print(f"  [관련도 {c.get('relevance')}] {t[:40]}")
        print(f"      for_me: {(c.get('for_me') or '')[:90]}")
    for r in user["rejected"]:
        print(f"  [반려] {r['title'][:40]} | {(r['reason'] or '')[:70]}")

    checks = {
        "전에_반려된_항목_과반_회복": len(revived) >= 2,
        "무관한_대조항목은_계속_반려": control_rejected,
        "살아난_카드에_for_me_있음": all((cards[t].get("for_me") or "").strip() for t in revived),
        "살아난_카드_관련도_기준_이상": all(r >= schemas.MIN_RELEVANCE for r in relevances) if relevances else False,
        "형식_실패_없음": not user["format_failed"],
    }
    report = {"checks": checks, "살아남": len(revived), "반려": len(rejected), "pass": all(checks.values())}
    print("\n" + json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
