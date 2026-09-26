"""가치 낮은 뉴스 거르기와 카드 문장 기준 검수 (2026-09-27). 네트워크·모델·DB를 쓰지 않는다.

실행: uv run python -m tests.pipeline.check_promo
- 규칙(pipeline/promo.py): 9/23 책 소개 연재·TechCrunch 자체 행사 홍보(세션·티켓·연사)는 빠지고,
  진짜 소식(행사 자리 발표·회의 개최 기사)과 도구는 남는다. 9/27 0시 후보 152건에서 사람(Claude Code) 판정 6건과 일치, 오탐 0
- 선별 프롬프트 worth_today에 행사·책·웨비나·채용 기준, 해설가·큐레이터 프롬프트에 문장 기준이 들어 있다
선별·해설가 프롬프트 효과는 로컬·Groq 모델로 전후 비교하지 않았다(2026-09-27 사용자 지시로 작업 중 모델 호출 중단). 9/27 07:00 실행 결과로 본다.
"""
import json
import sys

from agent import curator, explainer
from pipeline import promo


def news(title: str) -> dict:
    return {"type": "news", "title": title}


def main() -> int:
    promos = ["[AI리더의 서가] 요즘 AI 루프 엔지니어링",
              "TechCrunch Disrupt 2026: Ricursive Intelligence’s Anna Goldie and Azalia Mirhoseini on when AI starts designing its own hardware",
              "StrictlyVC San Francisco: an evening with founders", "[서평] 에이전트 설계 입문", "LLM 에이전트 실전 웨비나 참가자 모집",
              "Last 24 hours to save up to $200 on TechCrunch Disrupt 2026. Reason 5 of 5 to attend: Momentum",
              "Mark Wahlberg is coming to TechCrunch Disrupt 2026, and he wants to talk about your work"]
    real = ['"AI 에이전트 결제 전, 문자로 물어본다"...SKT, GSMA RCS 회의 개최',
            "OpenAI unveils new model at TechCrunch Disrupt", "새로운 최고 성능·가격 40% 인하…앤트로픽, '클로드 오퍼스 5.5' 공개",
            "Meta admits Muse’s likeness to OpenClaw isn’t a coincidence"]
    kept, dropped = promo.drop([news(t) for t in promos + real] + [{"type": "skill", "title": "[서평] 스킬"}])
    checks = {
        "홍보·연재_제목은_빠짐": [d["title"] for d in dropped] == promos,
        "빠진_이유_기록": [d["reason"] for d in dropped] == ["책 소개 연재", "행사 홍보", "행사 홍보", "책 소개 연재", "웨비나 안내", "행사 홍보", "행사 홍보"],
        "진짜_소식은_남음(개최·행사장_발표)": [k["title"] for k in kept if k["type"] == "news"] == real,
        "도구는_규칙_대상_아님": any(k["type"] == "skill" for k in kept),
        "선별_기준에_행사·책·웨비나·채용": all(w in curator.SELECT_PROMPT for w in ("행사·컨퍼런스 세션 예고", "책·서평·신간", "웨비나", "채용 공고")),
        "해설가_합니다체·3인칭금지·지어내기금지": all(w in explainer.PROMPT for w in ('"~합니다"체', "3인칭·호칭", "지어내지 않는다")),
        "해설가_뉴스_장단점_기준": "기사를 읽는 이점" in explainer.PROMPT,
        "큐레이터_why_구체·합니다체": "골랐습니다" in curator.PICK_PROMPT and "어느 항목에나 붙는 말" in curator.PICK_PROMPT,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
