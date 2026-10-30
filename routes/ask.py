"""질문창 API (W2, 계획안 부록 E). 세션 필요, 본인 질문만.

- POST /api/ask {question, force_unclear}: 한도 확인 → 게이트(in/out/unclear) → out은 고정 응답(답변 모델 미호출·한도 미차감)
  → in·unclear는 items 키워드 검색 → 해설가 답(fetch_article 최대 3회, 600자, 확인한 곳 링크) → questions 기록
- GET /api/ask: 오늘 대화와 남은 횟수
- 같은 날 앞선 턴은 맥락으로 붙인다: 최근 3턴 원문, 그 이전은 한 줄 요약(LLM 없이 질문·답 앞부분). out 턴은 넣지 않는다
- 연속 3회 out이면 질문 예시를 같이 준다. "AI 질문이었어요"(force_unclear)는 게이트를 건너뛰고 unclear로 다시 묻는다
- 후보가 없으면 모델을 부르지 않고 "우리 소스에서 못 찾음", 지시어만 있는 질문이면 "어느 도구 말씀이세요?"
- 한도(DAILY_QUESTION_LIMIT)는 in·unclear 턴 수. 넘으면 게이트도 부르지 않는다
질문 한 번이 트레이스 하나(ask 아래 gate·answer)이고 questions.trace_id에 남는다.
"""
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import exc as sa_exc
from sqlalchemy import case, func, insert, literal, or_, select

import db
import gate
import models
from agent import explainer, tracing
from pipeline.run_daily import today_kst
from routes.auth import require_approved

log = logging.getLogger("toolscout.ask")
router = APIRouter()

QUESTION_MAX = 300
RECENT_TURNS = 3
CANDIDATE_LIMIT = 5
SEARCH_POOL = 60
OUT_ANSWER = "이 질문창은 AI 소식과 MCP·스킬 같은 AI 도구 질문만 받아요. 브리핑에 나온 항목이나 찾는 도구를 물어봐 주세요."
NOT_FOUND = "우리 소스에서 못 찾았어요. 지어내지 않으려고 답을 비워 둘게요."
WHICH_TOOL = "어느 도구 말씀이세요? 도구 이름을 같이 적어 주세요."
FORMAT_FAILED = "답을 규격대로 만들지 못했어요. 질문을 조금 바꿔 다시 물어봐 주세요."
LIMIT_MESSAGE = "오늘 질문 한도를 다 썼어요. 내일 다시 물어봐 주세요."
UNAVAILABLE = "지금은 답을 만들 수 없어요. 잠시 뒤 다시 물어봐 주세요."
EXAMPLES = ["오늘 브리핑에 나온 MCP 중에 노션이랑 붙는 거 있어?", "낚시 앱 만들 때 쓸 만한 MCP 있어?", "요즘 나온 코딩 에이전트 소식 알려줘"]
KEYWORD_MAX = 8
# 한글로 읽어 쓴 이름("큐웬", "코덱스")을 영어 제목에서도 찾도록 영어 표기를 덧붙이는 사전 {한글: [영어]}
def load_terms() -> dict[str, list[str]]:
    """사전 파일이 없거나 깨져도 질문창은 확장 없이 돌아간다(앱 전체가 import에서 죽지 않게)."""
    terms: dict[str, list[str]] = {}
    try:
        raw = json.loads((Path(__file__).resolve().parents[1] / "agent" / "term_dict.json").read_text("utf-8"))
        for english, korean in raw.items():
            for ko in korean:
                terms.setdefault(ko, []).append(english)
    except (OSError, ValueError, AttributeError):
        log.warning("agent/term_dict.json을 읽지 못해 한영 이름 확장 없이 동작한다")
    return terms


TERMS = load_terms()
DEMONSTRATIVE = re.compile(r"그거|그것|이거|이것|저거|그 도구|그건|아까")
PARTICLE = re.compile(r"(이랑|에서|으로|이야|해줘|은|는|이|가|을|를|에|로|와|과|랑|의|도|만|야|줘)$")
STOPWORDS = {"있어", "있나", "있을까", "어때", "알려", "알려줘", "뭐야", "뭐가", "관련", "오늘", "브리핑", "그거", "이거", "저거",
             "설치", "명령", "추천", "어떤", "쓸만한", "만한", "나온", "중에", "대해", "어떻게", "요즘", "소식", "그리고", "사용",
             "방법", "좋은", "무슨", "없어", "해줘", "궁금해"}


class AskBody(BaseModel):
    question: str
    force_unclear: bool = False


def question_limit() -> int:
    try:
        return max(0, int(os.environ.get("DAILY_QUESTION_LIMIT", "10")))
    except ValueError:
        return 10


def today_turns(user_id: int, day) -> list:
    with db.get_engine().connect() as conn:
        return conn.execute(select(db.Question).where(db.Question.user_id == user_id, db.Question.session_date == day)
                            .order_by(db.Question.turn_no)).all()


def context_turns(turns: list) -> list[dict]:
    """최근 3턴 원문, 그 이전은 한 줄 요약. out 턴은 뺀다 (게이트를 우회하려는 문장을 맥락에 다시 넣지 않게)."""
    useful = [t for t in turns if t.gate != "out"]
    older, recent = useful[:-RECENT_TURNS], useful[-RECENT_TURNS:]
    return ([{"turn_no": t.turn_no, "summary": f"질문 {t.question[:50]} / 답 {(t.answer or '')[:70]}"} for t in older]
            + [{"turn_no": t.turn_no, "question": t.question, "answer": t.answer, "sources": t.sources_json or []} for t in recent])


def keywords(question: str) -> list[str]:
    """질문의 핵심어. 사전에 있는 한글 이름은 영어 표기를 바로 뒤에 덧붙인다(원래 한글 낱말은 그대로 둔다)."""
    words: list[str] = []
    for raw in re.findall(r"[0-9A-Za-z가-힣.+#-]+", question):
        word = raw.strip(".-")
        stripped = PARTICLE.sub("", word) if re.search(r"[가-힣]$", word) else word
        word = stripped if len(stripped) >= 2 else word
        if len(word) >= 2 and word.lower() not in STOPWORDS and word not in words:
            words.append(word)
        for english in TERMS.get(raw.lower()) or TERMS.get(word.lower()) or []:
            if english not in words:
                words.append(english)
    return words[:KEYWORD_MAX]


def find_candidates(user_id: int, question: str, turns: list) -> list[dict]:
    """앞선 턴의 출처 항목 + 키워드가 든 항목. 점수는 제목 일치 2·요약이나 원문 설명 일치 1, 같으면 내 브리핑에 나온 것·최신 순."""
    words = keywords(question)
    context_urls = [s["url"] for t in turns[-RECENT_TURNS:] if t.gate != "out" for s in (t.sources_json or [])]
    columns = (db.Item.id, db.Item.title, db.Item.url, db.Item.type, db.Item.source, db.Item.date, db.Item.summary_ko,
               db.Item.description)
    with db.get_engine().connect() as conn:
        rows = list(conn.execute(select(*columns).where(db.Item.url.in_(context_urls)))) if context_urls else []
        if words:
            # "MCP"처럼 흔한 단어는 수백 건이 걸리므로 최신순이 아니라 일치 점수순으로 자르고, 내 브리핑 항목은 따로 가져온다
            matched = or_(*[or_(db.Item.title.ilike(f"%{w}%"), db.Item.summary_ko.ilike(f"%{w}%"), db.Item.description.ilike(f"%{w}%"))
                            for w in words])
            points = sum((case((db.Item.title.ilike(f"%{w}%"), 2), (db.Item.summary_ko.ilike(f"%{w}%"), 1),
                               (db.Item.description.ilike(f"%{w}%"), 1), else_=0) for w in words), literal(0))
            ordered = select(*columns).where(matched).order_by(points.desc(), db.Item.date.desc()).limit(SEARCH_POOL)
            rows += conn.execute(ordered).all()
            rows += conn.execute(ordered.join(db.Briefing, db.Briefing.item_id == db.Item.id)
                                 .where(db.Briefing.user_id == user_id)).all()
        ids = list({r.id for r in rows})
        mine = {r.item_id: r for r in conn.execute(select(db.Briefing.item_id, db.Briefing.date, db.Briefing.card_json)
                                                   .where(db.Briefing.user_id == user_id, db.Briefing.item_id.in_(ids))
                                                   .order_by(db.Briefing.date))} if ids else {}

    def score(row) -> tuple:
        text = (row.title or "").lower(), f"{row.summary_ko or ''} {row.description or ''}".lower()
        hits = sum(2 if w.lower() in text[0] else 1 if w.lower() in text[1] else 0 for w in words)
        return (row.url in context_urls, hits, row.id in mine, row.date)

    unique = {r.id: r for r in rows}.values()
    ranked = [r for r in sorted(unique, key=score, reverse=True) if r.url in context_urls or score(r)[1] > 0][:CANDIDATE_LIMIT]
    candidates = []
    for row in ranked:
        entry = {"title": row.title, "url": row.url, "type": row.type, "source": row.source, "date": str(row.date),
                 "summary_ko": (row.summary_ko or "")[:300], "description": (row.description or "")[:300]}
        if row.id in mine and mine[row.id].card_json:
            card = mine[row.id].card_json
            entry["my_briefing_date"] = str(mine[row.id].date)
            entry["card"] = {k: card.get(k) for k in ("summary_ko", "for_me", "install_cmd", "pros", "cons")}
        candidates.append(entry)
    return candidates


def save_turn(user_id: int, day, question: str, gate_value: str, answer: str, sources: list[dict], trace_id: str) -> int:
    """turn_no는 그날 마지막 번호 + 1. 동시에 두 번 보내 번호가 겹치면 한 번 더 센다."""
    for attempt in (1, 2):
        try:
            with db.get_engine().begin() as conn:
                last = conn.execute(select(func.max(db.Question.turn_no)).where(db.Question.user_id == user_id,
                                                                                db.Question.session_date == day)).scalar()
                turn_no = (last or 0) + 1
                conn.execute(insert(db.Question).values(user_id=user_id, session_date=day, turn_no=turn_no, question=question,
                                                        gate=gate_value, answer=answer, sources_json=sources, trace_id=trace_id,
                                                        created_at=db.utcnow()))
            return turn_no
        except sa_exc.IntegrityError:
            if attempt == 2:
                raise
    raise RuntimeError("unreachable")


def _turn(row) -> dict:
    return {"turn_no": row.turn_no, "question": row.question, "gate": row.gate, "answer": row.answer, "sources": row.sources_json or []}


@router.get("/api/ask")
def history(user: db.User = Depends(require_approved)) -> dict:
    turns = today_turns(user.id, today_kst())
    limit = question_limit()
    return {"turns": [_turn(t) for t in turns], "limit": limit,
            "remaining": max(0, limit - sum(1 for t in turns if t.gate != "out"))}


@router.post("/api/ask")
async def ask(body: AskBody, user: db.User = Depends(require_approved)) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문을 적어 주세요")
    if len(question) > QUESTION_MAX:
        raise HTTPException(status_code=400, detail=f"질문은 {QUESTION_MAX}자까지 받아요")
    if models.dev_mode() and not user.is_test:
        raise HTTPException(status_code=403, detail="개발 모드에서는 테스트 계정만 질문할 수 있어요")
    day = today_kst()
    turns = today_turns(user.id, day)
    limit = question_limit()
    used = sum(1 for t in turns if t.gate != "out")
    if used >= limit:
        raise HTTPException(status_code=429, detail=LIMIT_MESSAGE)
    previous = context_turns(turns)
    profile = {"role": user.role, "tools_tags": user.profile_tools_tags or []}
    with tracing.span("ask", kind="chain", input={"question": question, "force_unclear": body.force_unclear,
                                                  "previous_turns": previous}) as span:
        try:
            if body.force_unclear:
                verdict = {"gate": "unclear", "reason": "사용자가 AI 질문이었다고 다시 보냄"}
            else:
                verdict = await gate.classify(question, previous)
            sources: list[dict] = []
            if verdict["gate"] == "out":
                text = OUT_ANSWER
            else:
                candidates = find_candidates(user.id, question, turns)
                if not candidates:
                    text = WHICH_TOOL if DEMONSTRATIVE.search(question) else NOT_FOUND
                else:
                    result = await explainer.answer(question, verdict["gate"], candidates, previous, profile, user_id=user.id)
                    text = result["answer"] if result["status"] == "ok" else FORMAT_FAILED
                    sources = result["sources"]
        except Exception as exc:  # 모델 장애·MCP 연결 실패는 기록하지 않고 한도도 쓰지 않는다
            log.warning("질문 답변 실패(%s)", type(exc).__name__)
            span.update(output={"error": type(exc).__name__}, level="WARNING")
            raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
        span.update(output={"gate": verdict, "answer": text, "sources": sources})
        trace_id = span.trace_id
    turn_no = save_turn(user.id, day, question, verdict["gate"], text, sources, trace_id)
    response = {"turn_no": turn_no, "gate": verdict["gate"], "answer": text, "sources": sources,
                "remaining": max(0, limit - used - (verdict["gate"] != "out"))}
    recent = [t.gate for t in turns[-2:]] + [verdict["gate"]]
    if len(recent) == 3 and all(g == "out" for g in recent):
        response["examples"] = EXAMPLES
    return response
