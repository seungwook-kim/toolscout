"""n8n 워크플로우 JSON 검수 (계획안 9.2 W1). n8n을 띄우지 않고 파일 구조를 본다. 실제 가져오기는 CI(n8n 컨테이너)가 한다.

실행: uv run python -m tests.n8n.check_workflows
- 노드 종류·typeVersion이 docker-compose의 n8n 2.38.7(n8n-nodes-base 2.38.2)에 있는 값인지
- 07:00·08:00 크론, 시간대 Asia/Seoul, 연결이 모두 있는 노드를 가리키는지
- 부르는 주소·메서드가 routes/w1.py에 있는지, 메일 노드가 쓰는 필드를 발송함이 주는지
- 개발 모드 분기에서는 메일 노드에 닿지 않는지
- 비밀값이 파일에 없는지 (서비스 키·메일 주소·$env 없음, 자격 증명은 이름 참조만)
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from pipeline import briefing_mail
from routes import w1

ROOT = Path(__file__).resolve().parents[2]
W1 = ROOT / "n8n" / "workflows" / "W1_daily.json"
# n8n-nodes-base 2.38.2 노드 정의에서 확인한 버전 (2026-09-15, npm pack)
NODE_VERSIONS = {
    "n8n-nodes-base.scheduleTrigger": {1, 1.1, 1.2, 1.3, 1.4},
    "n8n-nodes-base.httpRequest": {3, 4, 4.1, 4.2, 4.3, 4.4, 4.5},
    "n8n-nodes-base.if": {2, 2.1, 2.2, 2.3},
    "n8n-nodes-base.splitOut": {1},
    "n8n-nodes-base.emailSend": {2, 2.1},
}
APP = "http://app:8000"
SECRET = re.compile(r"X-Service-Key|@gmail\.com|\$env|app_?password|Bearer ", re.I)


def reachable(connections: dict, start: str, output: int | None = None) -> set[str]:
    """start에서 이어지는 노드 이름. output을 주면 그 출력 칸에서만 출발한다."""
    seen: set[str] = set()
    outputs = connections.get(start, {}).get("main", [])
    stack = [link["node"] for i, links in enumerate(outputs) if output is None or i == output for link in links]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack += [link["node"] for links in connections.get(name, {}).get("main", []) for link in links]
    return seen


def main() -> int:
    raw = W1.read_text(encoding="utf-8")
    flow = json.loads(raw)
    nodes = {n["name"]: n for n in flow["nodes"]}
    by_type = lambda t: [n for n in flow["nodes"] if n["type"] == t]
    crons = sorted(i["expression"] for n in by_type("n8n-nodes-base.scheduleTrigger") for i in n["parameters"]["rule"]["interval"])
    routes = {(method, route.path) for route in w1.router.routes for method in route.methods}
    calls = {(n["parameters"].get("method", "GET"), n["parameters"]["url"].removeprefix(APP)) for n in by_type("n8n-nodes-base.httpRequest")}
    targets = {link["node"] for c in flow["connections"].values() for links in c["main"] for link in links}
    email = by_type("n8n-nodes-base.emailSend")[0]
    used_fields = set(re.findall(r"\$json\.(\w+)", json.dumps(email["parameters"])))
    sample = briefing_mail.render(date(2000, 1, 1), "역할", [])
    outbox_fields = {"user_id", "from", "to", "role", "cards", "empty_reason", "trace_ids", *sample}
    if_node = by_type("n8n-nodes-base.if")[0]["name"]
    checks = {
        "노드_종류·버전_n8n_2.38에_있음": all(n["type"] in NODE_VERSIONS and n["typeVersion"] in NODE_VERSIONS[n["type"]] for n in flow["nodes"]),
        "노드_이름_중복_없음": len(nodes) == len(flow["nodes"]),
        "크론_07시·08시": crons == ["0 7 * * *", "0 8 * * *"],
        "시간대_Asia/Seoul": flow["settings"].get("timezone") == "Asia/Seoul",
        "연결이_있는_노드만_가리킴": set(flow["connections"]) <= set(nodes) and targets <= set(nodes),
        "부르는_API가_routes/w1에_있음": all(url.startswith("/api/w1/") for _, url in calls)
        and calls <= {(m, p) for m, p in routes},
        "HTTP_노드는_서비스키_자격증명": all(n.get("credentials", {}).get("httpHeaderAuth", {}).get("name") == "toolscout 서비스 키"
                                        for n in by_type("n8n-nodes-base.httpRequest")),
        "메일_필드는_발송함이_줌": used_fields <= outbox_fields and {"to", "subject", "html", "text", "from"} <= used_fields,
        "메일_노드는_SMTP_자격증명·n8n_서명_끔": email.get("credentials", {}).get("smtp", {}).get("name") == "toolscout Gmail SMTP"
        and email["parameters"]["options"].get("appendAttribution") is False,
        "개발모드_분기는_메일에_안닿음": email["name"] not in reachable(flow["connections"], if_node, 0)
        and email["name"] in reachable(flow["connections"], if_node, 1),
        "메일_성공만_발송기록": reachable(flow["connections"], email["name"], 0) == {"발송 기록"}
        and not reachable(flow["connections"], email["name"], 1),
        "비밀값_없음": not SECRET.search(raw),
        "가져올때_꺼진_상태": flow["active"] is False,
    }
    report = {"file": str(W1.relative_to(ROOT)), "nodes": len(nodes), "calls": sorted(calls), "checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
