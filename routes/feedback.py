"""피드백 API (W3, 계획안 부록 C). 웹앱은 세션으로, 메일 버튼은 서명 링크(사용자·항목·버튼, 24시간, 1회용)로.

- POST /api/feedback {item_id, action}: 관심없음 -1·써봤음 +1·이상함 기록, 같은 버튼 재클릭은 취소 (memory.apply_feedback)
- POST /api/feedback/{id}/note {reason | memo}: 이상함 사유 3택, 써봤음 메모
- POST /api/feedback/link {token}: 메일 링크. /f 화면의 스크립트가 부른다 (메일 보안 검사기가 링크를 미리 열어도 기록되지 않게)
- POST /api/feedback/link/note {token, reason}: 메일 링크로 기록한 이상함의 사유 (1시간 서명 토큰)
만료·위조 링크는 "링크가 만료됐어요", 기록하지 않는다.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db
import memory
from routes import tokens
from routes.auth import base_url, require_approved

LINK_TTL = 24 * 3600
NOTE_TTL = 3600
router = APIRouter()


class FeedbackBody(BaseModel):
    item_id: int
    action: str
    reason: str | None = None
    memo: str | None = None


class NoteBody(BaseModel):
    reason: str | None = None
    memo: str | None = None


class LinkBody(BaseModel):
    token: str


class LinkNoteBody(BaseModel):
    token: str
    reason: str


def feedback_link(user_id: int, item_id: int, action: str) -> str:
    """메일 카드 버튼 링크."""
    from urllib.parse import quote

    return f"{base_url()}/f?t={quote(tokens.sign('feedback', {'u': user_id, 'i': item_id, 'a': action}, LINK_TTL))}"


def _apply(user_id: int, item_id: int, action: str) -> dict:
    try:
        return memory.apply_feedback(user_id, item_id, action)
    except memory.FeedbackError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.post("/api/feedback")
def post_feedback(body: FeedbackBody, user: db.User = Depends(require_approved)) -> dict:
    result = _apply(user.id, body.item_id, body.action)
    if result["status"] == "recorded" and (body.reason or body.memo):
        note(result["feedback_id"], NoteBody(reason=body.reason, memo=body.memo), user)
    return result


@router.post("/api/feedback/{feedback_id:int}/note")  # :int가 없으면 /api/feedback/link/note를 이 경로가 먼저 잡는다
def note(feedback_id: int, body: NoteBody, user: db.User = Depends(require_approved)) -> dict:
    try:
        return memory.note_feedback(user.id, feedback_id, reason=body.reason, memo=body.memo)
    except memory.FeedbackError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.post("/api/feedback/link")
def post_link(body: LinkBody) -> dict:
    try:
        data = tokens.consume(body.token, "feedback")
    except tokens.TokenError as exc:
        detail = "이미 누른 링크예요. 웹앱에서 바꿀 수 있어요" if exc.reason == "used" else "링크가 만료됐어요"
        raise HTTPException(status_code=400, detail=detail) from None
    result = _apply(data["u"], data["i"], data["a"])
    if result["status"] == "recorded" and data["a"] == "이상함":
        result["note_token"] = tokens.sign("feedback_note", {"u": data["u"], "f": result["feedback_id"]}, NOTE_TTL)
    return result | {"action": data["a"]}


@router.post("/api/feedback/link/note")
def post_link_note(body: LinkNoteBody) -> dict:
    try:
        data = tokens.verify(body.token, "feedback_note")
    except tokens.TokenError:
        raise HTTPException(status_code=400, detail="링크가 만료됐어요") from None
    try:
        return memory.note_feedback(data["u"], data["f"], reason=body.reason)
    except memory.FeedbackError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
