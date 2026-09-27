"""선별 재현율·정밀도 채점 (계획안 품질 지표 "선별 재현율·정밀도", 목표 각 90%). 모델을 부르지 않는다.

실행: uv run python -m tests.golden.score_select [--date 2026-09-27]   (날짜를 빼면 정답 파일이 있는 날 전부)
- 정답: tests/golden/select_<날짜>.json (사람이 단 O/X, 기준은 파일의 rubric)
- 모델 판정: tests/golden/run_select_<날짜>.json (fetch_select.py가 트레이스에서 꺼낸 그날 실행의 판정)
- 뉴스만 채점한다. 모델이 고른 것 = ai_related이고 worth_today. 제목으로 맞추고 한쪽에만 있는 항목은 따로 센다
- 95% 신뢰구간은 윌슨 구간. 건수가 적으면 넓다 (계획안: 골든셋 수치는 보조 지표)
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
TARGET = 0.9


def wilson(hits: int, total: int) -> list[float] | None:
    if not total:
        return None
    z, p = 1.96, hits / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(center - half, 3), round(center + half, 3)]


def score(day: str) -> dict:
    golden = json.loads((HERE / f"select_{day}.json").read_text(encoding="utf-8"))
    run = json.loads((HERE / f"run_select_{day}.json").read_text(encoding="utf-8"))
    truth = {i["title"]: i["label"] == "O" for i in golden["items"]}
    picked = {j["title"]: bool(j["ai_related"] and j["worth_today"]) for j in run["judgments"] if j["type"] == "news"}
    both = [t for t in truth if t in picked]
    tp = sum(truth[t] and picked[t] for t in both)
    fp = [t for t in both if picked[t] and not truth[t]]
    fn = [t for t in both if truth[t] and not picked[t]]
    selected, relevant = tp + len(fp), tp + len(fn)
    precision = tp / selected if selected else None
    recall = tp / relevant if relevant else None
    return {
        "date": day, "scored": len(both), "only_golden": len(truth) - len(both), "only_run": len(picked) - len(both),
        "answer_O": relevant, "model_selected": selected, "true_positive": tp,
        "precision": round(precision, 3) if precision is not None else None, "precision_ci95": wilson(tp, selected),
        "recall": round(recall, 3) if recall is not None else None, "recall_ci95": wilson(tp, relevant),
        "meets_target_90": bool(precision is not None and recall is not None and precision >= TARGET and recall >= TARGET),
        "wrongly_selected": fp, "wrongly_dropped": fn,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    day = parser.parse_args().date
    days = [day] if day else sorted(p.stem.removeprefix("select_") for p in HERE.glob("select_*.json"))
    days = [d for d in days if (HERE / f"run_select_{d}.json").exists()]
    reports = [score(d) for d in days]
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 0 if reports else 1


if __name__ == "__main__":
    sys.exit(main())
