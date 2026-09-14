"""하루 실행 검수 (계획안 9.2 W1, 부록 B 5·6, 예외 처리 표).

실행
- uv run python -m tests.pipeline.run_daily --fake : 가짜 모델 + 가짜 항목으로 검증 노드·저장·재실행 멱등·모델 장애·카드 0건 행을
  Supabase에 실제로 확인 (날짜 2000-01-01로 저장하고 끝나면 지운다. 모델 한도를 쓰지 않는다)
- uv run python -m tests.pipeline.run_daily [--users 1 --limit 40] : 실제 수집·실제 모델로 한 번 → tests/pipeline/daily_report.json
"""
import asyncio
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from langchain_core.messages import AIMessage
from sqlalchemy import delete, func, select, update

import db
import memory
import models
from agent import schemas, tracing
from pipeline import run_daily, validate
from tests.app.check_main import KEY, free_port, start

HERE = Path(__file__).parent
FAKE_DAY = date(2000, 1, 1)
FAKE_HOST = "https://example.test/"
KOREAN = {"summary_ko": "테스트 도구가 새 버전을 냈다. 설치 절차가 짧아졌다.", "for_me": "사내 브리핑 봇을 만들 때 참고할 수 있다."}
ENGLISH = {"summary_ko": "Test tool released a new version today.", "for_me": "Useful when building an internal bot."}
OUTAGE = models.ModelUnavailable("explainer", ["ollama 타임아웃", "groq 키 없음", "gemini 429", "openrouter 429"])


def _data(messages) -> dict:
    return json.loads(re.search(r"<data>\n(.*)\n</data>", messages[-1].content, re.S).group(1))


def fake_model(mode: str = "normal"):
    """큐레이터 3종·해설가 요청을 시스템 프롬프트로 구분해 정해진 답을 준다.

    mode: normal / outage_backend(백엔드 카드 해설 전부 모델 장애, 마케터는 전부 반려) / dead(모든 호출 모델 장애)
    """
    broken_once: set[str] = set()

    def call(role, messages, tools=None):
        if mode == "dead":
            raise OUTAGE
        system, data = messages[0].content, _data(messages)
        if '"judgments"' in system:
            body = {"judgments": [{"id": i["id"], "ai_related": True, "worth_today": True, "topic": "agent_framework",
                                   "reason": "검수용 판정"} for i in data]}
        elif '"empty_reason"' in system:
            body = {"news": [{"id": i["id"], "why": "검수용 선택 이유"} for i in data["news"][:5]],
                    "tools": [{"id": i["id"], "why": "검수용 선택 이유"} for i in data["tools"][:3]], "empty_reason": None}
        elif '"requests"' in system:
            body = {"requests": []}
        else:
            title, url, retry = data["item"]["title"], data["item"]["url"], "검증 노드가 직전 카드를" in system
            marketer = data["profile"]["role"] == "마케터"
            if mode == "outage_backend" and not marketer:
                raise OUTAGE
            if mode == "outage_backend" or ("REJECT" in title and marketer):
                body = {"reject": True, "reject_reason": "마케터 업무와 이어지는 쓰임이 없다"}
            elif "BROKEN" in title and title not in broken_once:
                broken_once.add(title)
                return AIMessage('{"summary_ko": "끊긴 응답')
            elif "ALWAYS_ENGLISH" in title or ("ENGLISH" in title and not retry):
                body = ENGLISH | {"pros": [{"text": "Easy to install", "evidence_url": url}]}
            else:
                body = KOREAN | {"pros": [{"text": "설치가 쉽다", "evidence_url": url}]}
        return AIMessage(json.dumps(body, ensure_ascii=False))
    return call


def fake_items() -> list[dict]:
    news = ["검수 뉴스 BROKEN 한 번 끊김", "ENGLISH 첫 응답만 영어", "ALWAYS_ENGLISH 계속 영어", "REJECT 마케터만 반려"]
    rows = [{"title": t, "url": f"{FAKE_HOST}news/{n}", "type": "news", "source": "aitimes"} for n, t in enumerate(news)]
    rows += [{"title": t, "url": f"{FAKE_HOST}repo", "type": "mcp", "source": "mcp_registry"} for t in ("검수 MCP 알파", "검수 MCP 베타")]
    return [r | {"published_at": "2000-01-01T00:00:00+00:00", "summary": "검수용 항목"} for r in rows]


def rows_for(user_ids: list[int]) -> dict:
    with db.get_engine().connect() as c:
        briefings = c.execute(select(db.Briefing.user_id, db.Briefing.item_id, db.Briefing.trace_id, db.Briefing.sent_at,
                                     db.Briefing.card_json, db.Briefing.empty_reason)
                              .where(db.Briefing.date == FAKE_DAY, db.Briefing.user_id.in_(user_ids))).all()
        item_ids = [r[0] for r in c.execute(select(db.Item.id).where(db.Item.url.like(f"{FAKE_HOST}%")))]
        seen = c.execute(select(db.Seen.user_id, func.count()).where(db.Seen.item_id.in_(item_ids)).group_by(db.Seen.user_id)).all()
    return {"briefings": briefings, "seen": dict(seen)}


def cleanup() -> None:
    with db.get_engine().begin() as c:
        item_ids = [r[0] for r in c.execute(select(db.Item.id).where(db.Item.url.like(f"{FAKE_HOST}%")))]
        c.execute(delete(db.Seen).where(db.Seen.item_id.in_(item_ids)))
        c.execute(delete(db.Briefing).where(db.Briefing.date == FAKE_DAY))
        c.execute(delete(db.Item).where(db.Item.id.in_(item_ids)))


def unit_checks() -> dict:
    card = {"type": "news", "title": "t", "url": "https://a.test/x", "why_this_card": "이유", "source_checked": True,
            "trace_id": "abc", "pros": [{"text": "설치가 쉽다", "evidence_url": "https://a.test/x"}], **KOREAN}
    named = "Anthropic이 Claude Code에 스킬 기능을 추가했다. 에이전트가 SKILL.md 설명서를 불러 반복 작업을 처리한다."
    letters = [ch for ch in named if re.match(r"[가-힣A-Za-z]", ch)]
    char_ratio = sum(1 for ch in letters if re.match(r"[가-힣]", ch)) / len(letters)
    pool = [{"type": "news", "source": s, "published_at": f"2000-01-0{d}", "title": f"n{d}"}
            for d, s in [(1, "hackernews"), (2, "openai"), (3, "aitimes"), (4, "openai"), (5, "geeknews"), (6, "hackernews")]]
    pool += [{"type": "mcp", "source": "mcp_registry", "stars": s, "title": f"t{s}"} for s in (5, 500, 50)]
    top = run_daily.top_items(pool, 4)
    return {
        "정상_카드_통과": validate.problems(card) == [],
        "영어_카드_한글비율_실패": any("한글 비율" in p for p in validate.problems(card | ENGLISH)),
        "제품명_많은_한국어_요약_통과(어절 기준)": validate.hangul_ratio(named) >= 0.6 > char_ratio,
        "for_me_두_문장_실패": any("한 문장" in p for p in validate.problems(card | {"for_me": "첫 문장이다. 둘째 문장이다."})),
        "근거_링크_다르면_실패": any("근거 링크" in p for p in validate.problems(
            card | {"pros": [{"text": "설치가 쉽다", "evidence_url": "https://other.test"}]})),
        "근거_링크_없으면_실패": bool(validate.problems(card | {"pros": [{"text": "설치가 쉽다"}]})),
        "요약_120자_넘으면_실패": bool(validate.problems(card | {"summary_ko": "가" * 121})),
        "trace_id_없으면_실패": bool(validate.problems(card | {"trace_id": ""})),
        "limit_상위N_비율유지·공식최신·별순": [i["title"] for i in top] == ["n4", "n2", "n3", "t500"],
        "옵션_users·limit_해석": vars(run_daily.parse_args(["--users", "1", "--limit", "40"]))
        | {"mcp_url": None} == {"users": 1, "limit": 40, "mcp_url": None},
    }


async def fake_run(mcp_url: str) -> dict:
    user_ids = memory.test_user_ids()
    backend, marketer = user_ids[0], user_ids[1]
    run = lambda mode="normal", **kw: run_daily.run(FAKE_DAY, items=fake_items(), mcp_url=mcp_url, model_call=fake_model(mode), **kw)
    first = await run()
    after_first = rows_for(user_ids)
    second = await run()
    after_second = rows_for(user_ids)
    outage = await run("outage_backend")
    after_outage = rows_for(user_ids)
    dead = await run("dead")
    after_dead = rows_for(user_ids)
    with db.get_engine().begin() as c:
        c.execute(update(db.Briefing).where(db.Briefing.date == FAKE_DAY, db.Briefing.user_id == backend)
                  .values(sent_at=datetime.now(timezone.utc)))
    one_user = await run(users=1)
    users = {u["user_id"]: u for u in first["users"]}
    card_rows = lambda rows, uid: [b for b in rows["briefings"] if b[0] == uid and b[1] is not None]
    empty_rows = lambda rows, uid: [b for b in rows["briefings"] if b[0] == uid and b[1] is None]
    failures_file = json.loads(run_daily.FORMAT_FAILURES.read_text(encoding="utf-8")) if run_daily.FORMAT_FAILURES.exists() else []
    return {
        "first": {k: first[k] for k in ("totals", "trace_id", "providers", "format_failures_recorded")} | {"users": [
            {k: u.get(k) for k in ("user_id", "status", "cards", "rejected", "excluded", "retried")} for u in first["users"]]},
        "outage": {k: outage[k] for k in ("totals", "all_users_failed", "model_failures")},
        "dead": {k: dead[k] for k in ("totals", "all_users_failed")} | {"exit_code": run_daily.exit_code(dead)},
        "checks": unit_checks() | {
            "is_test_사용자_2명만": sorted(users) == sorted(user_ids) and len(user_ids) == 2,
            "영어_첫응답_재시도후_살아남음": all("ENGLISH 첫 응답만 영어" in u["titles"] for u in users.values()),
            "계속_영어면_제외_이유기록": all(any(e["title"] == "ALWAYS_ENGLISH 계속 영어" and "한글 비율" in " ".join(e["reasons"])
                                            for e in u["excluded"]) for u in users.values()),
            "마케터만_반려_이유기록": [r["title"] for r in users[marketer]["rejected"]] == ["REJECT 마케터만 반려"]
                                     and not users[backend]["rejected"],
            "같은_저장소_MCP_앞순위만_저장": all(len(u["duplicates"]) == 1 for u in users.values()),
            "저장수_일치": len(after_first["briefings"]) == first["totals"]["cards"] > 0,
            "sent_at_null": all(b[3] is None for b in after_first["briefings"]),
            "카드마다_실행_trace_id": all(b[2] == first["trace_id"] == b[4]["trace_id"] for b in after_first["briefings"]),
            "card_json에_원문없음": all(set(b[4]) <= set(schemas.Card.model_fields) | {"rank"} for b in after_first["briefings"]),
            "seen_저장": sum(after_first["seen"].values()) == len(after_first["briefings"]),
            "형식실패_재시도복구·파일에_쌓임": first["totals"]["unrecovered"] == 0 and first["format_failures_recorded"] >= 1
                                          and any(r.get("label", "").startswith("카드") for r in failures_file),
            "재실행_같은_건수(멱등)": len(after_second["briefings"]) == len(after_first["briefings"])
                                    and after_second["seen"] == after_first["seen"] and second["totals"]["cards"] == first["totals"]["cards"],
            "카드_모델장애_사용자는_건너뜀·기존행_유지": outage["users"][0]["status"] == "model_failed"
                                                   and len(card_rows(after_outage, backend)) == len(card_rows(after_second, backend)),
            "카드0건_사용자는_empty_reason_행": [u["status"] for u in outage["users"] if u["user_id"] == marketer] == ["empty"]
                                               and len(empty_rows(after_outage, marketer)) == 1 and not card_rows(after_outage, marketer)
                                               and "반려" in (empty_rows(after_outage, marketer)[0][5] or "")
                                               and empty_rows(after_outage, marketer)[0][2] == outage["trace_id"]
                                               and after_outage["seen"].get(marketer, 0) == 0,
            "일부_장애는_종료코드_0": not outage["all_users_failed"] and run_daily.exit_code(outage) == 0,
            "전사용자_장애면_종료코드_2·저장없음": dead["all_users_failed"] and run_daily.exit_code(dead) == 2
                                              and after_dead["briefings"] == after_outage["briefings"],
            "users_1이면_발송안한_첫_사용자만": one_user["skipped_sent_users"] == [backend]
                                            and [u["user_id"] for u in one_user["users"]] == [marketer],
        },
    }


def live_report(report: dict) -> dict:
    checks = {
        "대상_사용자_모두_브리핑_저장": report["totals"]["users"] > 0 and report["totals"]["briefings"] == report["totals"]["users"],
        "모델장애_사용자_없음": report["totals"]["failed_users"] == 0,
        "트레이스_URL": bool(report["trace_url"]),
    }
    with db.get_engine().connect() as c:
        rows = c.execute(select(db.Briefing.trace_id, db.Briefing.sent_at).where(
            db.Briefing.date == date.fromisoformat(report["date"]),
            db.Briefing.user_id.in_([u["user_id"] for u in report["users"]]))).all()
    checks["저장_행마다_trace_id·sent_at_null"] = bool(rows) and all(r[0] and r[1] is None for r in rows)
    return report | {"checks": checks}


def main() -> int:
    os.environ["MCP_SERVICE_KEY"] = KEY
    port = free_port()
    proc = start(port)
    mcp_url = f"http://127.0.0.1:{port}/mcp"
    fake = "--fake" in sys.argv
    try:
        if fake:
            run_daily.FORMAT_FAILURES = Path(tempfile.gettempdir()) / "toolscout_fake_format_failures.json"
            run_daily.FORMAT_FAILURES.unlink(missing_ok=True)
            cleanup()
            try:
                report = asyncio.run(fake_run(mcp_url))
            finally:
                cleanup()
        else:
            args = run_daily.parse_args([a for a in sys.argv[1:] if a != "--fake"])
            report = live_report(asyncio.run(run_daily.run(mcp_url=mcp_url, users=args.users, limit=args.limit)))
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        tracing.flush()
    report["pass"] = all(report["checks"].values())
    if not fake:
        (HERE / "daily_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
