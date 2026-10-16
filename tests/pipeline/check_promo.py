"""가치 낮은 뉴스 거르기와 카드 문장 기준 검수 (2026-09-27). 네트워크·모델·DB를 쓰지 않는다.

실행: uv run python -m tests.pipeline.check_promo
- 규칙(pipeline/promo.py): 9/23 책 소개 연재·TechCrunch 자체 행사 홍보(세션·티켓·연사)는 빠지고,
  진짜 소식(행사 자리 발표·회의 개최 기사)과 도구는 남는다. 9/27 0시 후보 152건에서 사람(Claude Code) 판정 6건과 일치, 오탐 0
- 10/5 제목 규칙: [게시판] 단신·[기고] 의견 글·[영상] 강연·지난해 이전 연도를 단 예전 자료·OpenAI 블로그 고객 사례. 골든셋 정답 O는 안 걸림
- 선별 프롬프트 worth_today에 행사·책·웨비나·채용 기준, 해설가·큐레이터 프롬프트에 문장 기준이 들어 있다
선별·해설가 프롬프트 효과는 로컬·Groq 모델로 전후 비교하지 않았다(2026-09-27 사용자 지시로 작업 중 모델 호출 중단). 9/27 07:00 실행 결과로 본다.
"""
import json
import sys
from datetime import date
from pathlib import Path

from agent import curator, explainer
from pipeline import promo


def news(title: str) -> dict:
    return {"type": "news", "title": title}


def title_rules() -> dict:
    """10/5 추가: 단신 묶음·기고·강연 영상·예전 자료·OpenAI 고객 사례. 정답 파일(tests/golden/select_*.json)의 O는 하나도 안 걸려야 한다."""
    this_year = date.today().year
    cases = {"[게시판] KT, AI면접 서비스 출시 등 단신": "단신 묶음", "[기고] AI판 빅맥지수가 비춘 그림자": "칼럼·기고",
             "Greg Kroah-Hartman – Security in the LLM Age [video]": "강연 영상", f"Identity Management for Agentic AI [pdf] ({this_year - 1})": "예전 자료",
             f"올해 나온 에이전트 논문 ({this_year})": None, "게시판 기능을 AI로 바꾼 오픈소스 공개": None}
    customer = [({"type": "news", "source": "openai", "title": t}, want) for t, want in (
        ("How Albertsons Companies is reimagining retail from the inside out", "고객 사례"),
        ("Chatham scales its capital markets expertise with OpenAI", "고객 사례"), ("A model guide for the GPT-6 family", None),
        ("Disrupting a coordinated model-distillation campaign", None),
        # 10/16: 10/8~10/11에 규칙을 지나 모델까지 간 고객 사례와, 걸리면 안 되는 OpenAI 자기 발표
        ("How Oracle turns days of work into minutes with ChatGPT and Codex", "고객 사례"),
        ("Sophos cuts threat investigation time by 96% with OpenAI Daybreak", "고객 사례"),
        ("Asana cuts model costs 76x in browser tests with GPT-6.1 Sol", "고객 사례"),
        ("LegalOn halves Codex costs while maintaining development speed", "고객 사례"),
        ("Advancing computer use with Ironclad", "고객 사례"), ("Radisson Hotel Group brings hotel discovery into ChatGPT", "고객 사례"),
        ("OpenAI cuts API prices by 50%", None), ("ChatGPT doubles context window", None), ("Introducing GPT-6 with memory", None),
        ("Atlassian and OpenAI expand partnership to turn enterprise knowledge into action", None))]
    customer.append(({"type": "news", "source": "techcrunch", "title": "How startups are using OpenAI models"}, None))
    golden = [i for path in sorted(Path("tests/golden").glob("select_*.json")) for i in json.loads(path.read_text(encoding="utf-8"))["items"]]
    caught = [(i["label"], promo.reason({"type": "news", **i})) for i in golden]
    return {
        "단신·기고·강연·예전자료_제목은_빠짐(올해_연도·일반_단어는_남음)": all(promo.reason(news(t)) == want for t, want in cases.items()),
        "고객_사례는_OpenAI_블로그만": all(promo.reason(item) == want for item, want in customer),
        "정답_O는_하나도_안걸림(골든셋_전체)": not [r for label, r in caught if r and label == "O"] and sum(1 for _, r in caught if r) >= 21,
    }


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
        **title_rules(),
        "요약_빈_뉴스는_선별_입력에_링크_사이트(10/5)": curator._brief({"type": "news", "source": "hackernews", "title": "Muse Gadgets",
                                                              "url": "https://www.about.meta.com/a", "summary": ""}, 1).get("link_site") == "about.meta.com"
        and "link_site" not in curator._brief({"type": "news", "source": "aitimes", "title": "t", "url": "https://a.test/x", "summary": "요약"}, 2)
        and "link_site" not in curator._brief({"type": "mcp", "source": "mcp_registry", "title": "t", "url": "https://github.com/a/b", "summary": ""}, 3),
        "선별_기준에_행사·책·웨비나·채용": all(w in curator.SELECT_PROMPT for w in ("행사·컨퍼런스 세션 예고", "책·서평·신간", "웨비나", "채용 공고")),
        "선별_기준에_에세이·사용기_false·투자·장애·예고_true(9/30 골든셋)": all(w in curator.SELECT_PROMPT for w in (
            "에세이·칼럼·의견 글", "개인 사용기", "투자 유치", "서비스 장애", "신제품 발표 예고")),
        "해설가_합니다체·3인칭금지·지어내기금지": all(w in explainer.PROMPT for w in ('"~합니다"체', "3인칭·호칭", "지어내지 않는다")),
        "해설가_뉴스_장단점_기준": "기사를 읽는 이점" in explainer.PROMPT,
        "큐레이터_why_구체·합니다체": "골랐습니다" in curator.PICK_PROMPT and "어느 항목에나 붙는 말" in curator.PICK_PROMPT,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
