"""MCP 발송 전 검증과 검증 메모 검수 (2026-09-26). 네트워크·모델·DB를 쓰지 않는다.

왜: 9/16~9/26 발송분 점검에서 카드로 나간 MCP 24장 중 10장은 검증 요청이 없었는데 "검증 예정"으로 나갔다.
    스킬 위험 신호 "확인 필요" 줄은 내부 표시("모델:")와 마크다운이 그대로 나가 이유를 알 수 없었다.
실행: uv run python -m tests.verify.check_mcp_now
"""
import asyncio
import json
import sys
from datetime import date
from types import SimpleNamespace

from pipeline import briefing_mail, presend, rollback, verification

DAY = date(2000, 1, 1)


def mcp(n: int) -> dict:
    return {"type": "mcp", "title": f"검수 MCP {n}", "url": f"https://example.test/mcp-{n}", "summary": "검수용",
            "install": {"packages": [{"registryType": "npm", "identifier": f"pkg-{n}"}]}}


def skill(n: int) -> dict:
    return {"type": "skill", "title": f"검수 스킬 {n}", "url": f"https://example.test/skill-{n}", "skill_url": "https://example.test/SKILL.md"}


def run_with(plans: list[dict], known: dict | None = None, fail_on: int | None = None, step: float = 0.0) -> tuple[dict, dict]:
    """verification·verifier를 가짜로 바꿔 probe_mcps_now만 돌린다. step: 검증 한 건마다 흐르는 가짜 시계 초."""
    log: dict = {"requests": [], "saved": []}
    before = (verification.results_for, verification.save_requests, verification.item_id_for, presend.verifier.run)
    now = [0.0]

    async def fake_run(requests, **kwargs):
        log["requests"] += requests
        now[0] += step
        if requests[0]["item_id"] == fail_on:
            raise RuntimeError("검수용 실패")
        return {"items": [{"status": "done"}], "counts": {"done": 1}}

    verification.results_for = lambda urls: {u: v for u, v in (known or {}).items() if u in urls}
    verification.save_requests = lambda day, requests: log["saved"].append((day, [r["url"] for r in requests])) or len(requests)
    verification.item_id_for = lambda url: int(url.rsplit("-", 1)[-1]) + 100
    presend.verifier.run = fake_run
    try:
        result = asyncio.run(presend.probe_mcps_now({"plans": plans}, DAY, None, "http://x/mcp", clock=lambda: now[0]))
        return result, log
    finally:
        (verification.results_for, verification.save_requests, verification.item_id_for, presend.verifier.run) = before


def main() -> int:
    plans = [{"user_id": 1, "tools": [mcp(1), skill(1)], "related": [mcp(2)]},
             {"user_id": 2, "tools": [mcp(1), mcp(3)], "related": []}]
    result, log = run_with(plans)
    urls = [r["url"] for r in log["requests"]]
    known = {mcp(1)["url"]: {"verification": {"install": {}}, "request_status": "done"},
             mcp(2)["url"]: {"request_status": "rejected", "note": "실측 불가(도커 이미지)"},
             mcp(3)["url"]: {"request_status": "pending", "note": "다음 날 06:00 검증 예정"}}
    skipped, skipped_log = run_with(plans, known=known)
    many, many_log = run_with([{"user_id": 1, "tools": [mcp(n) for n in range(1, 8)], "related": []}])
    slow, slow_log = run_with([{"user_id": 1, "tools": [mcp(n) for n in range(1, 5)], "related": []}], step=presend.MCP_BUDGET_SECONDS / 2)
    broken, broken_log = run_with([{"user_id": 1, "tools": [mcp(1), mcp(2)], "related": []}], fail_on=101)
    none, none_log = run_with([{"user_id": 1, "tools": [skill(1)], "related": []}])

    row = lambda kind, status, error=None, attempts=0: (kind, status, error, attempts)  # noqa: E731
    notes = {args: verification.request_note(*args) for args in (
        row("mcp", "pending"), row("skill", "pending"), row("mcp", "incomplete", "E2B 시간 초과", 1),
        row("mcp", "incomplete", "E2B 시간 초과", verification.MAX_ATTEMPTS), row("mcp", "rejected", "실측 불가(도커 이미지)"),
        row("mcp", "done", "설치법 미확인"))}
    attached = rollback.attach([mcp(1), skill(1), {"type": "news", "url": "https://example.test/n"}, mcp(2)],
                               {mcp(2)["url"]: {"request_status": "pending", "note": "다음 날 06:00 검증 예정"}})
    review = SimpleNamespace(status="done", risk_signal="unverified", purpose=None, trigger=None, steps_summary=None, tools_needed=None,
                             completeness=None, regex_hits=[], reviewed_at=DAY,
                             risk_quote="모델: **This is the most critical field** — it is\n\nloaded " + "x" * 300)
    risk = verification.card_risk(review)
    regex_basis, _ = verification.readable_quote("정규식: `base64 -d`")
    plain_basis, plain = verification.readable_quote("curl -LsSf https://a.test/install.sh | sh")
    line = briefing_mail.verify_lines({"type": "skill", "risk_signal": risk})[0]

    checks = {
        "MCP만_검증·관련카드_포함": set(urls) == {mcp(1)["url"], mcp(2)["url"], mcp(3)["url"]},
        "같은_MCP는_한_번(사용자_순서)": urls == [mcp(1)["url"], mcp(2)["url"], mcp(3)["url"]],
        "요청_모양": all(r["kind"] == "mcp" and r["depth"] == "full" and r["install"].get("install") for r in log["requests"]),
        "요청_행_먼저_저장": log["saved"] and log["saved"][0][0] == DAY and set(log["saved"][0][1]) == set(urls),
        "결과_집계": result["asked"] == 3 and result["statuses"] == ["done"] * 3 and result["deferred"] == 0,
        "결과있는것·실패·거부는_건너뛰고_대기는_지금": [r["url"] for r in skipped_log["requests"]] == [mcp(3)["url"]]
        and skipped["skipped"] == 2,
        "한_실행_한도·나머지는_다음날로": len(many_log["requests"]) == presend.MCP_PROBE_LIMIT and many["deferred"] == 7 - presend.MCP_PROBE_LIMIT
        and len(many_log["saved"][0][1]) == 7,
        "시간_예산_넘으면_새로_시작_안함": len(slow_log["requests"]) == 2 and slow["deferred"] == 2,
        "한_건_실패해도_나머지_계속": broken["statuses"] == ["error", "done"] and len(broken_log["requests"]) == 2,
        "MCP가_없으면_아무것도_안함": none["asked"] == 0 and not none_log["requests"] and not none_log["saved"],
        "메모_대기는_다음날_06시": notes[row("mcp", "pending")] == "다음 날 06:00 검증 예정"
        and notes[row("skill", "pending")] == "다음 날 06:00 판독 예정",
        "메모_미완료는_이유·재시도_여부": notes[row("mcp", "incomplete", "E2B 시간 초과", 1)] == "검증 미완료(E2B 시간 초과), 다음 날 다시"
        and notes[row("mcp", "incomplete", "E2B 시간 초과", verification.MAX_ATTEMPTS)] == "검증 미완료(E2B 시간 초과)",
        "메모_거부·설치법미확인은_이유_그대로": notes[row("mcp", "rejected", "실측 불가(도커 이미지)")] == "실측 불가(도커 이미지)"
        and notes[row("mcp", "done", "설치법 미확인")] == "설치법 미확인",
        "요청없는_도구카드는_검증안함": [c["verification_note"] for c in attached] == ["검증 안 함", "판독 안 함", None, "다음 날 06:00 검증 예정"],
        "메일에_검증예정이_사실없이_안나옴": "검증 예정" not in briefing_mail.verify_lines(attached[0])[0],
        "확인필요_근거는_읽을수있는_말로": risk["basis"] == "판독 모델만 위험으로 봄" and regex_basis == "규칙 검사만 위험으로 봄"
        and plain_basis is None and plain.startswith("curl"),
        "인용문_마크다운·줄바꿈_걷고_자름": "**" not in risk["quote"] and "\n" not in risk["quote"]
        and len(risk["quote"]) <= verification.QUOTE_MAX and risk["quote"].endswith("…"),
        "메일_줄_모양": line.startswith('SKILL.md 읽어봤더니: 위험 신호 확인 필요 (판독 모델만 위험으로 봄) "This is the most critical field'),
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
