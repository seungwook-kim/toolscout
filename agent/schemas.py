"""에이전트 출력 JSON 규격. 큐레이터·해설가가 만들고 검증 노드(pipeline/validate.py)가 같은 규격으로 검사한다.

pydantic 모델로 두어 모델 출력 검증과 문서화를 한 곳에서 한다.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# 주제 10개 (고정). 계획안에 목록이 없어 2026-09-14 초안을 만들고 같은 날 사용자가 확정했다. 여기 한 곳에서만 고친다
TOPICS: dict[str, str] = {
    "model_release": "모델 출시·성능",
    "agent_framework": "에이전트·프레임워크",
    "mcp_tools": "MCP·도구 연동",
    "coding_tools": "코딩 도구·IDE",
    "pricing": "가격·요금·한도",
    "open_local": "오픈소스·로컬 모델",
    "data_rag": "데이터·검색·RAG",
    "safety_policy": "보안·안전·정책",
    "automation": "업무 자동화·노코드",
    "industry": "산업·투자·기업 동향",
}
TopicId = Literal["model_release", "agent_framework", "mcp_tools", "coding_tools", "pricing",
                  "open_local", "data_rag", "safety_policy", "automation", "industry"]

MAX_NEWS, MAX_TOOLS, MAX_VERIFY = 5, 3, 5
MAX_RELATED = 3  # 관련 카드(F3-b) 월요일 최대 장수 (2026-09-15 사용자 결정)


class Judgment(BaseModel):
    """선별: 항목 하나의 판정."""
    id: int
    ai_related: bool
    worth_today: bool
    topic: TopicId
    reason: str = Field(min_length=2, max_length=120)


class SelectionBatch(BaseModel):
    judgments: list[Judgment]


class Pick(BaseModel):
    """사용자별 후보 하나. why는 카드의 why_this_card로 이어진다."""
    id: int
    why: str = Field(min_length=2, max_length=120)


class UserPicks(BaseModel):
    news: list[Pick] = Field(default_factory=list, max_length=MAX_NEWS)
    tools: list[Pick] = Field(default_factory=list, max_length=MAX_TOOLS)
    empty_reason: str | None = None  # 뉴스·도구가 모두 0건일 때 "오늘 비움" 이유


class RelatedPicks(BaseModel):
    """관련 카드(F3-b) 선택. 날짜 무관 도구 목록에서 고른다."""
    tools: list[Pick] = Field(default_factory=list, max_length=MAX_RELATED)


class VerifyRequest(BaseModel):
    """검증관에 보낼 도구 항목. depth: full=설치 4단계, remote=원격 엔드포인트 확인, read=SKILL.md 판독."""
    id: int
    depth: Literal["full", "remote", "read"]
    reason: str = Field(min_length=2, max_length=120)


class VerifyRequests(BaseModel):
    requests: list[VerifyRequest] = Field(default_factory=list, max_length=MAX_VERIFY)


# 해설가 ------------------------------------------------------------------

MAX_SUMMARY, MAX_FOR_ME, MAX_POINTS = 120, 150, 3
MAX_DRAFT_SUMMARY = 600  # 해설가 초안은 길게 받아 검증 노드가 문장 끝에서 120자로 자른다
MIN_RELEVANCE = 3  # 해설가가 매긴 관련도(1~5)가 이보다 낮으면 카드를 반려한다 (2026-09-15 사용자 결정)
SOURCE_UNCHECKED = "원문 확인 필요"
COLLECTION_STALE = "수집 실패, 전날 기준"


class Evidence(BaseModel):
    """장점·단점 한 줄과 근거 링크 (링크 필수)."""
    text: str = Field(min_length=2, max_length=100)
    evidence_url: str = Field(pattern=r"^https?://\S+$")


class ExplainerOutput(BaseModel):
    """해설가 모델이 채우는 부분. 반려면 reject_reason만 있으면 된다.

    요약 길이·빈 값은 여기서 막지 않는다. 검증 노드가 두 단계로 처리한다 (1: 문장 끝에서 자름, 2: 이유를 돌려 1회 자가 수정).
    """
    reject: bool = False
    reject_reason: str | None = None
    relevance: int | None = Field(default=None, ge=1, le=5)
    summary_ko: str | None = Field(default=None, max_length=MAX_DRAFT_SUMMARY)
    for_me: str | None = Field(default=None, max_length=MAX_DRAFT_SUMMARY)
    pros: list[Evidence] = Field(default_factory=list, max_length=MAX_POINTS)
    cons: list[Evidence] = Field(default_factory=list, max_length=MAX_POINTS)
    install_cmd: str | None = None

    @model_validator(mode="after")
    def _complete(self):
        if self.reject and not (self.reject_reason or "").strip():
            raise ValueError("reject가 true면 reject_reason이 필요하다")
        return self


class Card(BaseModel):
    """카드 JSON (계획안 9.3). 검증 노드와 저장이 이 규격을 쓴다. verification·risk_signal은 검증관 단계에서 채운다."""
    item_id: int | None = None
    type: Literal["news", "mcp", "skill"]
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https?://\S+$")
    summary_ko: str = Field(min_length=1, max_length=MAX_SUMMARY)
    for_me: str = Field(min_length=1, max_length=MAX_FOR_ME)
    why_this_card: str = Field(min_length=1, max_length=120)
    pros: list[Evidence] = Field(default_factory=list, max_length=MAX_POINTS)
    cons: list[Evidence] = Field(default_factory=list, max_length=MAX_POINTS)
    verification: dict | None = None
    risk_signal: dict | None = None
    install_cmd: str | None = None
    relevance: int = Field(ge=MIN_RELEVANCE, le=5)  # 해설가가 매긴 이 사용자와의 관련도
    source_checked: bool
    notice: str | None = None  # "원문 확인 필요", "수집 실패, 전날 기준"을 " · "로 잇는다
    related: bool = False  # 관련 카드(F3-b, 월요일). 메일·화면에서 칸을 따로 둔다
    trace_id: str = Field(min_length=1)  # trace_id 없는 카드는 만들지 않는다 (작업 규칙 10)


class DraftCard(Card):
    """해설가가 만든 검증 전 카드. 요약이 길거나 비어 있을 수 있고, 검증 노드를 거쳐 Card가 된다."""
    summary_ko: str = Field(default="", max_length=MAX_DRAFT_SUMMARY)
    for_me: str = Field(default="", max_length=MAX_DRAFT_SUMMARY)
    relevance: int | None = Field(default=None, ge=1, le=5)


MAX_ANSWER = 600  # 질문 답 (부록 E). 초안은 넉넉히 받고 문장 끝에서 자른다
MAX_ANSWER_DRAFT = 1200


class AnswerSource(BaseModel):
    title: str = Field(default="", max_length=200)
    url: str = Field(pattern=r"^https?://\S+$")


class AnswerOutput(BaseModel):
    """질문 답변. found가 true면 sources에 입력 후보의 링크가 한 개 이상 있어야 한다 (호출부가 후보 링크만 남긴다)."""
    found: bool
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_DRAFT)
    sources: list[AnswerSource] = Field(default_factory=list, max_length=5)


# 검증관 (세션 8) --------------------------------------------------------------


class McpProbePlan(BaseModel):
    """검증관이 MCP 항목마다 정하는 다음 행동. probe면 설치 명령·종류, stop이면 이유("설치법 미확인", "실측 불가(명령 형식)")."""
    action: Literal["probe", "stop"]
    kind: Literal["npm", "pypi", "remote"] | None = None
    command: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=300)
    reason: str = Field(min_length=2, max_length=160)


class SkillJudgment(BaseModel):
    """검증관의 SKILL.md 판독. risk_signal은 모델 판정이고, 정규식과 다르면 최종은 확인 필요(unverified)."""
    purpose: str = Field(min_length=2, max_length=200)
    trigger: str = Field(min_length=2, max_length=200)
    steps_summary: str = Field(min_length=2, max_length=400)
    tools_needed: str = Field(default="", max_length=200)
    completeness: Literal["높음", "보통", "낮음"]
    risk_signal: Literal["ok", "caution"]
    risk_quote: str | None = Field(default=None, max_length=300)
