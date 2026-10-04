"""선별 채점(score_select.py) 검수 (2026-10-05). 임시 폴더의 가짜 정답·판정 파일로 확인하고 모델·DB·네트워크를 쓰지 않는다.

실행: uv run python -m tests.golden.check_score_select
- 전체 지표: 정밀도·재현율·오답 목록
- new_only: 앞선 날짜 판정 파일에 나온 제목은 빼고 센다(같은 기사를 놓친 것이 이틀 오답으로 세지지 않게). 뒤 날짜 파일은 보지 않는다
"""
import json
import sys
import tempfile
from pathlib import Path

from tests.golden import score_select


def write(here: Path, day: str, rows: list[tuple[str, str, bool]]) -> None:
    """rows: (제목, 정답 O/X, 모델 통과)."""
    (here / f"select_{day}.json").write_text(json.dumps({"items": [{"title": t, "label": label} for t, label, _ in rows]}), encoding="utf-8")
    judgments = [{"type": "news", "title": t, "ai_related": passed, "worth_today": passed} for t, _, passed in rows]
    (here / f"run_select_{day}.json").write_text(json.dumps({"judgments": judgments}), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        here = Path(tmp)
        write(here, "2026-10-03", [("레고 생성기", "O", False), ("새 모델 공개", "O", True)])
        write(here, "2026-10-04", [("레고 생성기", "O", False), ("새 모델 공개", "O", True), ("작은 도구", "O", False),
                                   ("큰 출시", "O", True), ("에세이", "X", True)])
        write(here, "2026-10-05", [("다음 날 기사", "O", True)])
        first, second = score_select.score("2026-10-03", here), score_select.score("2026-10-04", here)
    new = second["new_only"]
    checks = {
        "전체_지표": (second["answer_O"], second["true_positive"], second["model_selected"]) == (4, 2, 3)
        and second["recall"] == 0.5 and second["precision"] == 0.667 and second["wrongly_dropped"] == ["레고 생성기", "작은 도구"],
        "처음_본_것만_전날_제목_뺌": (new["scored"], new["repeated"], new["answer_O"], new["true_positive"]) == (3, 2, 2, 1)
        and new["recall"] == 0.5 and new["precision"] == 0.5,
        "첫날은_뺄_것_없음·뒤_날짜는_안봄": first["new_only"]["repeated"] == 0 and first["new_only"]["recall"] == first["recall"],
        "오답_목록은_전체에만": "wrongly_dropped" not in new,
    }
    report = {"checks": checks, "pass": all(checks.values())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
