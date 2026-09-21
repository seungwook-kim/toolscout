"""이름(io.github.x/y)으로만 쌓인 도구 목록 제목을 레지스트리 표시명으로 보정한다 (2026-09-21).

실행: uv run python -m tests.sources.backfill_titles
코드는 check_catalog_title로 고쳤고 이 스크립트는 이미 쌓인 행을 고친다. 레지스트리 검색이 건당 2~3초라
topic이 있는 도구 목록만 대상으로 한다. 2026-09-21 실행 결과: 고침 40, 표시명 없음 12, 못 찾음 0.
"""
import time
import httpx
from sqlalchemy import text
import db
from sources.mcp_registry import URL, display_title

with db.session() as s:
    rows = s.exec(text("""select id, title, version from items
                          where type in ('mcp','skill') and topic is not null
                            and (title like 'io.github%' or title like '%/%')
                          order by id""")).all()
print(f"보정 대상 {len(rows)}건", flush=True)
fixed, same, missed = 0, 0, []
with httpx.Client(timeout=15, headers={"User-Agent": "toolscout/1.0 (catalog title backfill)"}) as c:
    for item_id, title, version in rows:
        name = title.split(" ")[0]
        try:
            r = c.get(URL, params={"search": name, "limit": 20})
            servers = [e.get("server", e) for e in r.json().get("servers", [])]
            match = next((sv for sv in servers if sv.get("name") == name), None)
        except Exception as e:
            missed.append((name, type(e).__name__)); continue
        if not match:
            missed.append((name, "레지스트리에 없음")); continue
        new = display_title({**match, "version": version or match.get("version")})
        if new.split(" ")[0] == name:
            same += 1  # 레지스트리에도 표시명이 없다
            continue
        with db.session() as s:
            s.exec(text("update items set title = :t where id = :i").bindparams(t=new[:300], i=item_id))
            s.commit()
        print(f"  {name[:40]:42} -> {new[:45]}", flush=True)
        fixed += 1
print(f"\n고침 {fixed} · 표시명 없음 {same} · 못 찾음 {len(missed)}")
for n, why in missed[:8]:
    print(f"   - {n[:45]} ({why})")
