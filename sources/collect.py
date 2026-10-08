"""소스 전체 수집. 뉴스는 48시간, 도구(MCP·스킬)는 7일 창을 쓴다 (계획안 9.2 W1).

소스 하나가 실패해도 나머지로 진행하고 실패를 기록한다 (계획안 부록 B 예외 처리).
MCP 레지스트리는 자주 느리거나 500을 내서 (2026-09-14·15 실측) 제한 시간 60초로 2번 더 시도하고,
그래도 실패하면 마지막으로 성공한 결과를 다시 쓰고 항목에 "수집 실패, 전날 기준"을 붙인다 (2026-09-15 사용자 결정).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.schemas import COLLECTION_STALE
from sources import anthropic_skills, claude_notes, hackernews, mcp_registry, skillsmp
from sources.common import KST, SourceResult, error_text, http_client
from sources.rss import FEEDS, fetch_feed

# 뉴스 창 48시간. 하루 1회 07:00 실행이라 24시간이면 기사 하나가 후보에 오를 기회가 한 번뿐이고,
# 그 실행에서 밀리면 창 밖으로 나가 다시 후보가 되지 못한다. 실제로 9월 17일 17시 36분 기사(판단 전용 모델 Jev 공개)가
# 9월 18일 실행에서 밀린 뒤 9월 19일·20일 브리핑에 한 번도 오르지 못했다 (2026-09-21 실측).
# 이미 보낸 항목은 pick_for_user의 seen_urls와 items.url 유일 제약이 막는다
NEWS_WINDOW = timedelta(hours=48)
TOOL_WINDOW = timedelta(days=7)
MCP_TIMEOUT, MCP_RETRIES = 60, 2


def cache_dir() -> Path:
    """마지막 성공 결과를 두는 곳. 저장소 밖(사용자 로컬 데이터 폴더)."""
    base = os.environ.get("TOOLSCOUT_CACHE_DIR") or os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")), "toolscout")
    return Path(base)


def _last_success_path() -> Path:
    return cache_dir() / "mcp_registry_last.json"


def save_last_success(result: SourceResult, now: datetime) -> None:
    path = _last_success_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": str(now.astimezone(KST).date()), "items": result.items}, ensure_ascii=False),
                    encoding="utf-8")


def load_last_success(now: datetime) -> dict | None:
    """마지막 성공 결과. 도구 창(7일)보다 오래됐으면 쓰지 않는다."""
    path = _last_success_path()
    if not path.exists():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    saved_date = datetime.fromisoformat(saved["date"]).date()
    return saved if (now.astimezone(KST).date() - saved_date) <= TOOL_WINDOW else None


def collect_mcp(tool_since: datetime, now: datetime, *, per_publisher: int, cache: dict | None) -> SourceResult:
    attempts = []
    result = SourceResult("mcp_registry")
    with http_client(timeout=MCP_TIMEOUT) as client:
        for attempt in range(1, MCP_RETRIES + 2):
            try:
                result = mcp_registry.fetch(tool_since, client, per_publisher=per_publisher, cache=cache)
            except Exception as exc:  # 파서 버그도 다음 시도로
                result = SourceResult("mcp_registry", error=error_text(exc))
            attempts.append(result.error or "성공")
            if not result.error:
                break
    result.stats["시도"] = attempts
    if not result.error:
        save_last_success(result, now)
        return result
    previous = load_last_success(now)
    if previous:
        result.items = [item | {"collection_note": COLLECTION_STALE} for item in previous["items"]]
        result.stats["재사용한_성공_결과_날짜"] = previous["date"]
    return result


def collect(now: datetime | None = None, *, mcp_per_publisher: int = mcp_registry.MAX_PER_PUBLISHER,
            hn_min_points: int = hackernews.MIN_POINTS, cache: dict | None = None) -> list[SourceResult]:
    """cache를 넘기면 레지스트리 목록·버전 이력·별 수 조회를 재사용한다 (같은 날 필터 값만 바꿔 재측정할 때)."""
    now = now or datetime.now(timezone.utc)
    news_since, tool_since = now - NEWS_WINDOW, now - TOOL_WINDOW
    jobs = [(feed.name, lambda c, f=feed: fetch_feed(f, news_since, c)) for feed in FEEDS]
    jobs += [
        ("hackernews", lambda c: hackernews.fetch(news_since, c, min_points=hn_min_points)),
        # Claude 공식 릴리스 노트: Anthropic 발표(모델·요금·크레딧)를 원문으로 (2026-10-08, sources/claude_notes.py)
        (claude_notes.NAME, lambda c: claude_notes.fetch(news_since, c)),
        ("anthropic_skills", lambda c: anthropic_skills.fetch(tool_since, c)),
        # SkillsMP는 갱신 시각을 믿을 수 없어 창 대신 "아직 안 본 것"으로 고른다 (sources/skillsmp.py)
        ("skillsmp", lambda c: skillsmp.fetch(c)),
    ]
    results = []
    with http_client() as client:
        for name, job in jobs:
            try:
                results.append(job(client))
            except Exception as exc:  # 파서 버그도 전체 수집을 멈추지 않게
                results.append(SourceResult(name, error=error_text(exc)))
    results.append(collect_mcp(tool_since, now, per_publisher=mcp_per_publisher, cache=cache))
    return results
