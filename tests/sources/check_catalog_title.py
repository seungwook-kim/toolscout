"""도구 목록 제목 검수 (2026-09-21). 네트워크를 쓰지 않는다.

왜: 제목을 만드는 곳이 둘인데 규칙이 달랐다. 별 수 캐시(StarCache.flush)가 표시명을 보지 않고 이름만 저장했고,
두 upsert 모두 title을 갱신하지 않아 io.github.x/y 형태가 그대로 굳었다. 도구 목록 56건 중 55건이 그랬고,
9월 21일 관련 카드 11건이 전부 저장소 이름으로 나갔다.

실행: uv run python -m tests.sources.check_catalog_title
- display_title: 표시명이 있으면 표시명, 없으면 이름. 둘 다 버전을 붙인다
- 두 경로(선별 항목·별 수 캐시)가 같은 함수를 쓴다
- upsert 두 곳이 제목을 갱신하고, 빈 제목으로는 기존 값을 덮지 않는다
"""
import inspect
import json
import sys

from pipeline import persist
from sources import github_stars, mcp_registry

SERVER = {"name": "io.github.x/citra", "title": "Citra", "version": "5.0.2"}
NO_TITLE = {"name": "io.github.dat999zx/knowl", "version": "1.0.0"}


def main() -> int:
    registry_src = inspect.getsource(mcp_registry)
    stars_src = inspect.getsource(github_stars.save)
    catalog_src = inspect.getsource(persist.save_catalog)

    # 두 경로가 같은 함수를 쓰는지 (선별 항목 1곳 + 별 수 캐시 1곳 = 정의 1 + 호출 2)
    uses = registry_src.count("display_title(")

    checks = {
        "표시명이_있으면_표시명·버전": mcp_registry.display_title(SERVER) == "Citra 5.0.2",
        "표시명이_없으면_이름·버전": mcp_registry.display_title(NO_TITLE) == "io.github.dat999zx/knowl 1.0.0",
        "빈_서버는_빈_문자열": mcp_registry.display_title({}) == "",
        "버전이_없어도_공백이_남지_않음": mcp_registry.display_title({"title": "Citra"}) == "Citra",
        "두_경로가_같은_함수를_씀": uses >= 3,
        "별수캐시가_이름만_쓰지_않음": 'server.get("name", "")' not in stars_src,
        "별수캐시_upsert가_제목_갱신": '"title"' in stars_src and "nullif" in stars_src,
        "도구목록_upsert가_제목_갱신": '"title"' in catalog_src and "nullif" in catalog_src,
        "빈_제목으로_덮지_않음": stars_src.count("nullif") == 1 and catalog_src.count("nullif") == 1,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
