"""에이전트 출력 JSON 규격. 큐레이터·해설가가 만들고 검증 노드(pipeline/validate.py)가 같은 규격으로 검사한다.

pydantic 모델로 두어 모델 출력 검증과 문서화를 한 곳에서 한다.
"""
from typing import Literal

from pydantic import BaseModel, Field

# 주제 10개 (고정). 계획안에 목록이 없어 2026-09-14 초안으로 정했다. 확정 전까지 여기 한 곳에서만 고친다
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


class VerifyRequest(BaseModel):
    """검증관에 보낼 도구 항목. depth: full=설치 4단계, remote=원격 엔드포인트 확인, read=SKILL.md 판독."""
    id: int
    depth: Literal["full", "remote", "read"]
    reason: str = Field(min_length=2, max_length=120)


class VerifyRequests(BaseModel):
    requests: list[VerifyRequest] = Field(default_factory=list, max_length=MAX_VERIFY)
