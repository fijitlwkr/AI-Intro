"""같은 A* 설정·시드로 최초 계획과 매 행동 재계획을 각각 실행한다.

python -m runner.replanning --preset L2 --seeds 0-99 --heuristic mst --objective c1
결과: 모드별 원본 JSONL, 노션용 CSV, 상세 비교 JSON. 기존 로그 형식을 그대로 사용한다.
"""
import argparse
import csv
import json
import platform
from pathlib import Path
import subprocess
import sys

from agents.heuristics import HEURISTICS
from env import PRESETS
from .run import parse_seeds
from .summarize import load_rows, dedupe, summarize, common_table, trait_table, notion_table

ROOT = Path(__file__).resolve().parent.parent
MODES = ("never", "every_step")


def comparison(rows, seeds):
    """동일 조건의 모드별 로그가 모두 있는지 확인하고 시드별 비용 차이를 센다."""
    groups = {mode: {} for mode in MODES}
    conditions = set()
    for row in rows:
        if row["algorithm"] != "astar" or row["replan"] not in groups:
            raise ValueError("A*의 never/every_step 로그만 비교할 수 있습니다.")
        conditions.add((row["preset"], json.dumps(row["params"], sort_keys=True),
                        json.dumps(row["preset_params"], sort_keys=True), row["git_commit"]))
        groups[row["replan"]][row["seed"]] = row
    if len(conditions) != 1:
        raise ValueError("프리셋, 알고리즘 설정, 코드 버전이 같은 로그가 필요합니다.")
    if any(set(group) != set(seeds) for group in groups.values()):
        raise ValueError("두 모드가 요청한 모든 시드에서 실행돼야 합니다.")
    successful = [s for s in seeds if all(groups[m][s]["score_success"] for m in MODES)]
    deltas = [groups["every_step"][s]["score_cost"] - groups["never"][s]["score_cost"]
              for s in successful]
    return {
        "paired_games": len(seeds),
        "both_successful": len(successful),
        "every_step_cost_lower": sum(d < 0 for d in deltas),
        "equal_cost": sum(d == 0 for d in deltas),
        "every_step_cost_higher": sum(d > 0 for d in deltas),
        "cost_difference_mean_on_both_successful": sum(deltas) / len(deltas) if deltas else None,
    }


def print_table(head, body):
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in body:
        print("| " + " | ".join(str(value) for value in row) + " |")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=sorted(PRESETS), default="L2")
    parser.add_argument("--seeds", default="0-99")
    parser.add_argument("--heuristic", choices=HEURISTICS, default="mst")
    parser.add_argument("--objective", choices=("c1", "c2"), default="c1")
    parser.add_argument("--time-limit", type=float, default=60.0)
    parser.add_argument("--out-dir", default="logs/replanning_final")
    args = parser.parse_args(argv)
    seeds = sorted(set(parse_seeds(args.seeds)))
    if not seeds:
        parser.error("한 개 이상의 시드가 필요합니다.")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.preset}_{args.heuristic}_{args.objective}"
    paths = []
    for mode in MODES:
        path = out_dir / f"{prefix}_{mode}.jsonl"
        paths.append(path)
        # 별도 프로세스로 실행해 각 모드가 같은 초기 캐시 조건에서 시작한다.
        subprocess.run([
            sys.executable, "-m", "runner.run", "--agent", "astar", "--preset", args.preset,
            "--seeds", ",".join(map(str, seeds)), "--replan", mode,
            "--param", f"heuristic={args.heuristic}", "--param", f"objective={args.objective}",
            "--time-limit", str(args.time_limit), "--out", str(path),
        ], check=True, cwd=ROOT)
    rows, _ = dedupe(load_rows(paths))
    rows = [row for row in rows if row["seed"] in seeds]
    paired = comparison(rows, seeds)
    summary = summarize(rows)
    print("\n공통 지표")
    print_table(*common_table(summary))
    traits = trait_table(summary)
    if traits:
        print("\n특성 지표")
        print_table(*traits)
    csv_path = out_dir / f"{prefix}_notion.csv"
    head, body = notion_table(summary)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(head)
        writer.writerows(body)
    result = {
        "python_version": platform.python_version(), "preset": args.preset, "seeds": seeds,
        "heuristic": args.heuristic, "objective": args.objective,
        "time_limit_sec_per_game": args.time_limit, "paired": paired, "summary": summary,
        "model": "Current complaint only; no future new complaints in planning",
    }
    json_path = out_dir / f"{prefix}_comparison.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n같은 시드 비교: {json.dumps(paired, ensure_ascii=False)}")
    print(f"노션용 CSV: {csv_path}\n상세 결과: {json_path}")
    return result


if __name__ == "__main__":
    main()
