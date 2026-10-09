"""보호 2차 검수 (2026-10-09): 워터마크 · 함정 링크 · 요청 수 제한. 모델 호출 없음, 메일은 보내지 않는다(만들어 보기만).

실행: uv run python -m tests.web.check_protect2
- 워터마크: 넣기·풀기 왕복, 사용자마다 다름, API 응답·메일 본문(HTML·텍스트)에 들어감, 보이는 글자는 그대로, 문장 끝에 한 번만,
  데모 고정 표식, DB 원문에는 없음, 해독 명령(표식 없음·손상 안내 포함)
- 함정: 부르면 비로그인 403(robots.txt만 200), 로그인 세션은 통과, 다른 IP/UA는 영향 없음, HMAC만 저장, robots Disallow, 24시간 뒤 풀림(시각 조작)
- 제한: 기준 넘으면 429(한국어·Retry-After), 다음 창 회복, 사용자별·클라이언트별 따로, 로그인 API는 대상 아님, DB 실패 시 통과, 기본값
검수가 만든 DB 행(검수용 사용자·항목·차단·카운터)은 끝에 지운다. 시각은 guard.clock을 바꿔서 흉내 낸다.
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import timedelta
from pathlib import Path

from tests.web import common

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, insert, select  # noqa: E402

import db  # noqa: E402
from pipeline import briefing_mail, deliver  # noqa: E402
from pipeline.run_daily import today_kst  # noqa: E402
from routes import demo as demo_route, guard, watermark  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
A, B = "web-prot2-a@toolscout.test", "web-prot2-b@toolscout.test"
HOST = "https://example.test/web-prot2/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
IPS = {"trap": "198.51.100.10", "other": "198.51.100.11", "vip": "198.51.100.12", "later": "198.51.100.13", "rate": "198.51.100.20",
       "down": "198.51.100.99"}
ZW = "".join(watermark.ALPHABET)
STRIP = re.compile(f"[{ZW}]")
HIDDEN_PAGES = ("login", "signup", "demo", "index", "history", "settings")
FOOTER = "중요한 결정 전에는 원문 링크를 확인하세요."


def card(n: int) -> dict:
    return {"item_id": None, "type": "news", "title": f"검수 카드 {n}", "url": f"{HOST}{n}", "summary_ko": f"요약 {n}입니다.",
            "for_me": f"나한테는 {n}.", "why_this_card": f"이유 {n}.", "source_checked": True, "notice": None, "relevance": 4,
            "pros": [{"text": "좋은 점.", "evidence_url": f"{HOST}{n}"}], "cons": [{"text": "나쁜 점.", "evidence_url": f"{HOST}{n}"}],
            "install_cmd": None, "trace_id": f"trace-p2-{n}", "rank": n}


def seed(a_id: int, b_id: int) -> None:
    today = today_kst()
    with db.get_engine().begin() as c:
        for user_id in (a_id, b_id):
            item = c.execute(insert(db.Item).values(date=today, type="news", topic="pricing", title="검수 카드 1", url=f"{HOST}1-{user_id}",
                                                    summary_ko="요약 1입니다. 프로택트", source="test").returning(db.Item.id)).scalar_one()
            c.execute(insert(db.Briefing).values(user_id=user_id, date=today, item_id=item, rank=1, card_json=card(1) | {"item_id": item},
                                                 trace_id=f"trace-p2-{user_id}", pool_size=10))
        c.execute(db.User.__table__.update().where(db.User.id == a_id).values(is_test=True))


def cleanup() -> None:
    hashes = [guard.client_hash(ip, UA) for ip in IPS.values()] + [guard.client_hash(IPS["trap"], "Mozilla/5.0 other agent")]
    user_ids = [r[0] for r in db.get_engine().connect().execute(select(db.User.id).where(db.User.email.like("web-prot2-%")))]
    common.cleanup_users("web-prot2-")  # 브리핑을 먼저 지워야 항목을 지울 수 있다
    with db.get_engine().begin() as c:
        c.execute(delete(db.Item).where(db.Item.url.like(f"{HOST}%")))
        c.execute(delete(db.BlockedClient).where(db.BlockedClient.client_hash.in_(hashes)))
        c.execute(delete(db.RateCounter).where(db.RateCounter.key == "c:old-check"))
        c.execute(delete(db.RateCounter).where(db.RateCounter.key.in_([f"c:{h}" for h in hashes])))
        c.execute(delete(db.RateCounter).where(db.RateCounter.key.in_([f"u:{i}" for i in user_ids])))


def visible(text: str) -> str:
    return STRIP.sub("", text)


def flatten(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def boom(*_args, **_kwargs):
    raise RuntimeError("DB 문제")


def main() -> int:
    import main as app_main

    db.init_db()  # 새 표(blocked_clients, rate_counters)가 없으면 만든다(있으면 그대로)
    cleanup()
    real_clock, real_count, real_engine = guard.clock, guard.count_hit, db.get_engine
    base = time.time() // 60 * 60 + 5  # 1분 창의 시작 직후로 고정해 검수 도중 창이 바뀌지 않게
    guard.clock = lambda: base
    anon = TestClient(app_main.make_app(docs=False), base_url=common.BASE_URL, headers={"user-agent": UA})
    ca, cb = common.second_client(), common.second_client()
    checks: dict[str, bool] = {}
    try:
        common.login(ca, A)
        common.login(cb, B)
        for c in (ca, cb):
            c.headers.update({"user-agent": UA})
            c.post("/api/profile", json={"role": "개발자", "tools_tags": ["python"], "free_text": "검수용", "weights": {}})
        a_id, b_id = common.user_id(A), common.user_id(B)
        seed(a_id, b_id)
        mark_a, mark_b, mark_demo = watermark.mark_for(a_id), watermark.mark_for(b_id), watermark.mark_for(watermark.DEMO)

        # ---------- 워터마크 ----------
        today_a, today_b = ca.get("/api/briefings/today").json(), cb.get("/api/briefings/today").json()
        search_a = ca.get("/api/search?q=프로택트").json()
        demo = anon.get("/api/demo/briefing", headers={"x-forwarded-for": IPS["other"]}).json()
        sample = demo_route.sample()
        card_a, card_b = today_a["cards"][0], today_b["cards"][0]
        with db.get_engine().connect() as c:
            stored = c.execute(select(db.Briefing.card_json, db.Item.summary_ko).join(db.Item, db.Item.id == db.Briefing.item_id)
                               .where(db.Briefing.user_id == a_id)).first()
        text_fields = ("summary_ko", "for_me", "why_this_card")
        found, damaged = watermark.extract(card_a["summary_ko"] + " 중간 " + card_a["for_me"])
        ident = watermark.identify(card_a["summary_ko"], [(a_id, A), (b_id, B)])
        env = os.environ | {"PYTHONIOENCODING": "utf-8"}
        cli = subprocess.run([sys.executable, "-m", "routes.watermark", card_a["for_me"]], capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
        cli_none = subprocess.run([sys.executable, "-m", "routes.watermark", "표식 없는 글입니다"], capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
        broken = watermark.report(watermark.identify("글" + mark_a[:7] + "끝", [(a_id, A)]))
        checks.update({
            "표식_20자·0폭_문자만": len(mark_a) == watermark.MARK_LEN and set(mark_a) <= set(ZW)
            and all(unicodedata.category(ch) == "Cf" for ch in mark_a) and str(a_id) not in mark_a,
            "사용자마다_다름·데모_고정": len({mark_a, mark_b, mark_demo}) == 3 and watermark.mark_for(a_id) == mark_a,
            "API_카드_본문_글에_표식": all(card_a[k].endswith(mark_a) for k in text_fields) and card_a["pros"][0]["text"].endswith(mark_a)
            and card_a["cons"][0]["text"].endswith(mark_a),
            "다른_사용자는_다른_표식": all(card_b[k].endswith(mark_b) and mark_a not in card_b[k] for k in text_fields),
            "보이는_글자_그대로·문장_끝_한_번": visible(card_a["summary_ko"]) == "요약 1입니다." and visible(card_a["for_me"]) == "나한테는 1."
            and card_a["summary_ko"].count(mark_a) == 1 and not STRIP.search(card_a["summary_ko"][:-watermark.MARK_LEN]),
            "제목·링크·근거주소는_표식_없음": not STRIP.search(card_a["title"] + card_a["url"] + card_a["pros"][0]["evidence_url"]),
            "검색_결과_요약에도_표식": bool(search_a["results"]) and search_a["results"][0]["summary_ko"].endswith(mark_a)
            and not STRIP.search(search_a["results"][0]["title"] + search_a["results"][0]["url"]),
            "DB_원문에는_표식_없음": not STRIP.search(flatten(stored[0])) and not STRIP.search(stored[1]),
            "두_번_넣지_않음": watermark.mark_text(watermark.mark_text("글", mark_a), mark_a) == "글" + mark_a
            and watermark.mark_card(watermark.mark_card(card(1), mark_a), mark_a) == watermark.mark_card(card(1), mark_a),
            "원본_카드는_안_바뀜": (lambda c: (watermark.mark_card(c, mark_a), not STRIP.search(flatten(c)))[1])(card(2)),
            "풀기_왕복": len(found) == 2 and set(found) == {mark_a} and damaged == 0
            and ident["matches"] == [{"kind": "user", "id": a_id, "email": A, "count": 1}],
            "해독_명령": cli.returncode == 0 and A in cli.stdout and f"사용자 id {a_id}" in cli.stdout and B not in cli.stdout,
            "표식_없으면_없다고": cli_none.returncode == 0 and "표식이 없어요" in cli_none.stdout,
            "일부만_남으면_손상_안내": "일부만 남아" in broken,
            "데모_고정_표식": all(c["summary_ko"].endswith(mark_demo) and c["for_me"].endswith(mark_demo) for c in demo["cards"])
            and [visible(c["summary_ko"]) for c in demo["cards"]] == [c["summary_ko"] for c in sample["cards"]]
            and watermark.identify(demo["cards"][0]["summary_ko"], [(a_id, A)])["matches"][0]["kind"] == "demo",
        })
        # 메일: 본문(HTML·텍스트) 끝과 카드 글에 표식, 보이는 글자는 그대로
        plain = briefing_mail.render(today_kst(), "개발자", [card(1)])
        marked = briefing_mail.render(today_kst(), "개발자", [card(1)], mark=mark_a)
        outbox = [m for m in deliver.outbox(today_kst()) if m["user_id"] == a_id]
        checks.update({
            "메일_HTML·텍스트_끝에_표식": marked["html"].count(FOOTER + mark_a) == 1 and marked["text"].endswith(FOOTER + mark_a)
            and marked["html"].count(mark_a) >= 5,
            "메일_보이는_글자_그대로": visible(marked["html"]) == plain["html"] and visible(marked["text"]) == plain["text"]
            and marked["subject"] == plain["subject"] and not STRIP.search(plain["html"] + plain["text"]),
            "메일_제목·링크는_표식_없음": f'href="{HOST}1"' in marked["html"] and not STRIP.search(marked["subject"]),
            "발송_대기_메일에_받는_사람_표식": len(outbox) == 1 and outbox[0]["text"].endswith(FOOTER + mark_a)
            and outbox[0]["html"].count(FOOTER + mark_a) == 1 and mark_b not in outbox[0]["html"],
            "메일에는_함정_링크_없음": guard.TRAP_PATH not in marked["html"] + marked["text"] + (outbox[0]["html"] if outbox else ""),
        })

        # ---------- 함정 링크 ----------
        def get(path, ip, ua=UA, client=anon, **kw):
            return client.get(path, headers={"x-forwarded-for": ip, "user-agent": ua}, **kw)

        guard.clear_cache()
        robots = anon.get("/robots.txt").text
        pages = {n: (ROOT / "web" / f"{n}.html").read_text(encoding="utf-8") for n in HIDDEN_PAGES}
        link = re.compile(r'<a href="/archive/full-index" aria-hidden="true" tabindex="-1" style="[^"]*left:-9999px[^"]*">')
        before = get("/login", IPS["trap"]).status_code
        hit = get(guard.TRAP_PATH, IPS["trap"])
        after = {p: get(p, IPS["trap"]).status_code for p in ("/login", "/demo", "/api/demo/briefing", "/api/health", "/static/app.js")}
        robots_after = get("/robots.txt", IPS["trap"]).status_code
        other_ip = get("/login", IPS["other"]).status_code
        other_ua = get("/login", IPS["trap"], ua="Mozilla/5.0 other agent").status_code
        vip = get("/api/briefings/today", IPS["trap"], client=ca)  # 같은 IP·UA인데 로그인 세션이 있다
        vip_page = get("/", IPS["trap"], client=ca, follow_redirects=False).status_code
        vip_trap = get(guard.TRAP_PATH, IPS["vip"], client=ca)  # 세션 있는 요청이 함정을 불러도 기록하지 않는다
        vip_after = get("/login", IPS["vip"]).status_code
        with db.get_engine().connect() as c:
            row = c.execute(select(db.BlockedClient).where(db.BlockedClient.client_hash == guard.client_hash(IPS["trap"], UA))).first()
            mine = {guard.client_hash(ip, UA) for ip in IPS.values()}
            dumped = " ".join(str(v) for r in c.execute(select(db.BlockedClient)) if r.client_hash in mine for v in r)
        guard.clock = lambda: base + 23 * 3600
        guard.clear_cache()
        at_23h = get("/login", IPS["trap"]).status_code
        guard.clock = lambda: base + 24 * 3600 + 1
        guard.clear_cache()
        at_24h = get("/login", IPS["trap"]).status_code
        later_hit = get(guard.TRAP_PATH, IPS["later"])  # 24시간이 지난 시점에 다른 클라이언트가 걸리면 만료된 행이 정리된다
        with db.get_engine().connect() as c:
            old_gone = c.execute(select(db.BlockedClient).where(db.BlockedClient.client_hash == guard.client_hash(IPS["trap"], UA))).first() is None
        # 관리자가 차단 행을 지우면 1분 안에 풀린다(서버가 '차단 중'을 1분만 기억). 2026-10-09 운영 확인에서 찾은 문제
        later_base = base + 24 * 3600 + 1
        blocked_later = get("/login", IPS["later"]).status_code
        with db.get_engine().begin() as c:
            c.execute(db.BlockedClient.__table__.delete().where(db.BlockedClient.client_hash == guard.client_hash(IPS["later"], UA)))
        guard.clock = lambda: later_base + 30
        unblock_30s = get("/login", IPS["later"]).status_code
        guard.clock = lambda: later_base + 61
        unblock_61s = get("/login", IPS["later"]).status_code
        guard.clock = lambda: base
        guard.clear_cache()
        checks.update({
            "함정_robots_Disallow": f"Disallow: {guard.TRAP_PATH}\n" in robots and "Disallow: /\n" in robots,
            "함정_링크_6개_화면에_숨김": all(len(link.findall(t)) == 1 and t.index(guard.TRAP_PATH) > t.index("<body") for t in pages.values()),
            "부르기_전에는_200": before == 200,
            "차단_행_지우면_1분_안에_풀림": blocked_later == 403 and unblock_30s == 403 and unblock_61s == 200,
            "부르면_403": hit.status_code == 403 and "접근이 제한" in hit.text,
            "차단되면_비로그인_모든_요청_403": set(after.values()) == {403},
            "robots만은_200": robots_after == 200,
            "다른_IP·다른_UA는_영향_없음": other_ip == 200 and other_ua == 200,
            "로그인_세션은_통과": vip.status_code == 200 and vip_page == 200,
            "세션_요청의_함정은_기록_안_함": vip_trap.status_code == 403 and vip_after == 200,
            "HMAC만_저장·24시간": row is not None and len(row.client_hash) == 32 and IPS["trap"] not in dumped and "Mozilla" not in dumped
            and timedelta(hours=23, minutes=59) < row.expires_at - row.blocked_at <= timedelta(hours=24),
            "23시간_뒤에도_차단": at_23h == 403,
            "24시간_뒤_풀림": at_24h == 200,
            "만료_기록은_정리됨": later_hit.status_code == 403 and old_gone,
        })

        # ---------- 요청 수 제한 ----------
        os.environ.pop("RATE_LIMIT_OFF", None)
        os.environ["RATE_LIMIT_USER"], os.environ["RATE_LIMIT_ANON"] = "5", "3"
        rate = {"x-forwarded-for": IPS["rate"]}
        users_a = [ca.get("/api/briefings/dates").status_code for _ in range(5)]
        a_6 = ca.get("/api/briefings/dates")
        search_6 = ca.get("/api/search?q=프로택트").status_code
        b_1 = cb.get("/api/briefings/dates").status_code
        anon_ok = [anon.get("/api/demo/briefing", headers=rate).status_code for _ in range(3)]
        anon_4 = anon.get("/api/demo/briefing", headers=rate)
        anon_other = anon.get("/api/demo/briefing", headers={"x-forwarded-for": IPS["other"]}).status_code
        free = [ca.get("/api/me").status_code for _ in range(8)]  # 대상 아닌 경로
        login_try = [anon.post("/api/auth/login", json={"email": "nobody@toolscout.test", "password": "x"}, headers=rate).status_code for _ in range(5)]
        guard.clock = lambda: base + 60
        recovered = (ca.get("/api/briefings/dates").status_code, anon.get("/api/demo/briefing", headers=rate).status_code)
        guard.clock = lambda: base + 120
        guard.count_hit = boom
        db_down = (ca.get("/api/briefings/dates").status_code, anon.get("/api/demo/briefing", headers=rate).status_code)
        guard.count_hit = real_count
        db.get_engine = boom
        try:
            block_down = guard.is_blocked("없는-클라이언트")
            guard.clear_cache()
            health_down = anon.get("/api/health", headers={"x-forwarded-for": IPS["down"]}).status_code
        finally:
            db.get_engine = real_engine
            guard.clear_cache()
        guard.clock = lambda: base
        with db.get_engine().begin() as c:
            c.execute(insert(db.RateCounter).values(key="c:old-check", window=int(base // 60) - 100, count=1))
        guard.cleanup()
        with db.get_engine().connect() as c:
            old_counter = c.execute(select(db.RateCounter).where(db.RateCounter.key == "c:old-check")).first()
        os.environ.pop("RATE_LIMIT_USER"), os.environ.pop("RATE_LIMIT_ANON")
        defaults = (guard._limit("RATE_LIMIT_USER", guard.DEFAULT_USER_LIMIT), guard._limit("RATE_LIMIT_ANON", guard.DEFAULT_ANON_LIMIT))
        detail, retry = a_6.json().get("detail", ""), a_6.headers.get("retry-after", "")
        checks.update({
            "기준_안은_통과": users_a == [200] * 5 and anon_ok == [200] * 3,
            "기준_넘으면_429": a_6.status_code == 429 and anon_4.status_code == 429 and search_6 == 429,
            "429_한국어·Retry-After": "요청이 너무 많아요" in detail and retry.isdigit() and 1 <= int(retry) <= 60
            and anon_4.headers.get("retry-after", "").isdigit(),
            "사용자별·클라이언트별_따로": b_1 == 200 and anon_other == 200,
            "대상_아닌_경로·로그인은_안_셈": set(free) == {200} and 429 not in login_try,
            "다음_창에서_회복": recovered == (200, 200),
            "DB_실패하면_통과": db_down == (200, 200) and block_down is False and health_down == 200,
            "오래된_창_정리": old_counter is None,
            "운영_기본값_120·30·켜짐": defaults == (120, 30) and os.environ.get("RATE_LIMIT_OFF") != "1",
        })
    finally:
        guard.clock, guard.count_hit, db.get_engine = real_clock, real_count, real_engine
        guard.clear_cache()
        os.environ["RATE_LIMIT_OFF"] = "1"
        cleanup()
    ok = bool(checks) and all(checks.values())
    print(json.dumps({"checks": checks, "pass": ok}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
