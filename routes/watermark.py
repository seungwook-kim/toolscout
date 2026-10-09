"""사용자별 보이지 않는 워터마크 (2026-10-09 보호 2차). 글이 새어 나갔을 때 어느 계정에서 나왔는지 추적한다.

- 표식: SESSION_SECRET HMAC으로 만든 5바이트(40비트)를 0폭 문자 4종(2비트씩) 20개로 적는다. 사용자 id는 들어 있지 않다.
  표식에서 계정을 찾으려면 서버 비밀값으로 모든 사용자의 표식을 다시 만들어 맞춰 봐야 한다(아래 명령). 데모는 "데모" 고정 표식
- 0폭 문자 4종(U+200B, U+200C, U+200D, U+2060)은 복사·붙여넣기에서 대부분 살아남고 화면에는 아무것도 보이지 않는다
- 넣는 곳: 내보내는 카드 본문 글(요약·나한테는·이 카드인 이유·장점·단점 글)과 메일 본문 끝. 제목·링크·주소·설치 명령은 제외.
  글의 맨 끝(문장 끝)에 하나만 붙여서 화면 안 검색(Ctrl+F)이 단어 중간에서 끊기지 않는다. 같은 글에는 두 번 넣지 않는다
- DB에 저장된 원문에는 넣지 않는다. 내보낼 때(API 응답·메일 만들 때)만 복사본에 붙인다
- 정직한 한계: 손으로 다시 쓰거나 AI로 다시 쓰면 사라진다. 0폭 문자를 지우는 도구(일부 메신저·편집기·정규식)를 거쳐도 사라진다.
  일부만 지워지면 "손상"으로 알려 줄 뿐 계정은 못 찾는다. 짧은 구절만 베껴 가면 표식이 없는 부분일 수 있다.
  증거라기보다 단서다(HMAC 40비트라 우연히 겹칠 확률은 사용자 수/2의 40제곱 분의 1 정도로 아주 낮다)

해독 명령(관리자, DATABASE_URL·SESSION_SECRET이 있는 .env 필요):
    uv run python -m routes.watermark "<의심 글>"
    uv run python -m routes.watermark --file 의심글.txt
"""
import argparse
import re
import sys

from routes import tokens

ALPHABET = "\u200b\u200c\u200d\u2060"  # 2비트짜리 심볼 4개 (ZWSP, ZWNJ, ZWJ, 단어 접합자)
MARK_LEN = 20  # 심볼 20개 = 40비트
RUN = re.compile(f"[{ALPHABET}]+")
DEMO = "demo"


def mark_for(user_id: int | str) -> str:
    """사용자(또는 "demo") 한 명의 표식. 같은 비밀값이면 늘 같은 값."""
    digest = tokens.derive("watermark", str(user_id))[: MARK_LEN // 4]
    return "".join(ALPHABET[(byte >> shift) & 3] for byte in digest for shift in (6, 4, 2, 0))


def has_mark(text: str) -> bool:
    return any(len(run) >= MARK_LEN for run in RUN.findall(text or ""))


def mark_text(text: str | None, mark: str) -> str | None:
    """글 맨 끝에 표식을 붙인다. 비었거나 이미 표식이 있으면 그대로."""
    if not text or not mark or has_mark(text):
        return text
    return text + mark


def mark_card(card: dict, mark: str) -> dict:
    """카드 복사본의 본문 글에만 표식을 붙인다(제목·링크·근거 주소·설치 명령·원본 카드는 그대로)."""
    out = dict(card)
    for key in ("summary_ko", "for_me", "why_this_card"):
        if out.get(key):
            out[key] = mark_text(out[key], mark)
    for key in ("pros", "cons"):
        if out.get(key):
            out[key] = [{**point, "text": mark_text(point.get("text"), mark)} for point in out[key]]
    return out


def mark_cards(cards: list[dict], mark: str) -> list[dict]:
    return [mark_card(card, mark) for card in cards]


def extract(text: str) -> tuple[list[str], int]:
    """글에서 표식을 모두 찾는다. 반환: (온전한 표식 20심볼 목록, 손상된 0폭 문자 조각 수)."""
    found, damaged = [], 0
    for run in RUN.findall(text or ""):
        full, rest = divmod(len(run), MARK_LEN)
        found += [run[i * MARK_LEN:(i + 1) * MARK_LEN] for i in range(full)]
        damaged += 1 if rest else 0
    return found, damaged


def identify(text: str, users: list[tuple[int, str | None]]) -> dict:
    """users: [(id, 이메일)]. 반환: {found: 표식 수, damaged: 손상 조각 수, matches: [{kind, id, email, count}]}."""
    marks, damaged = extract(text)
    table = {mark_for(DEMO): ("demo", None, None)} | {mark_for(uid): ("user", uid, email) for uid, email in users}
    counts: dict[str, int] = {}
    for mark in marks:
        counts[mark] = counts.get(mark, 0) + 1
    matches = [{"kind": table[m][0], "id": table[m][1], "email": table[m][2], "count": n} for m, n in counts.items() if m in table]
    unknown = sum(n for m, n in counts.items() if m not in table)
    return {"found": len(marks), "damaged": damaged, "matches": matches, "unknown": unknown}


def report(result: dict) -> str:
    if result["matches"]:
        lines = ["표식을 찾았어요:"]
        for m in result["matches"]:
            who = "공개 데모(가입 없이 보는 예시)" if m["kind"] == "demo" else f"사용자 id {m['id']} ({m['email'] or '이메일 없음'})"
            lines.append(f"- {who} 표식 {m['count']}개")
        if result["unknown"]:
            lines.append(f"- 이 서버에서 만든 표식이 아닌 것 {result['unknown']}개(비밀값이 바뀌었거나 다른 서버/계정이 지워졌을 수 있어요)")
        if result["damaged"]:
            lines.append(f"- 일부만 남은 조각 {result['damaged']}개(무시함)")
        return "\n".join(lines)
    if result["found"] or result["unknown"]:
        return f"표식 {result['found']}개가 있지만 이 서버의 어느 계정과도 맞지 않아요(비밀값이 바뀌었거나 계정이 지워졌을 수 있어요)."
    if result["damaged"]:
        return f"표식이 일부만 남아 있어 계정을 찾을 수 없어요(손상된 조각 {result['damaged']}개). 중간에 일부가 지워진 글이에요."
    return "표식이 없어요. 표식이 지워졌거나(다시 쓰거나 AI로 고쳐 쓰면 사라져요), 이 서비스 밖에서 쓴 글일 수 있어요."


def main() -> int:
    parser = argparse.ArgumentParser(description="의심 글에서 워터마크를 읽어 어느 계정 표식인지 알려 준다")
    parser.add_argument("text", nargs="?", help="의심 글(따옴표로 감싸기)")
    parser.add_argument("--file", help="글이 든 파일(UTF-8)")
    args = parser.parse_args()
    text = open(args.file, encoding="utf-8").read() if args.file else (args.text if args.text is not None else sys.stdin.read())
    import db
    from sqlalchemy import select

    with db.get_engine().connect() as conn:
        users = [(row.id, row.email) for row in conn.execute(select(db.User.id, db.User.email))]
    print(report(identify(text, users)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
