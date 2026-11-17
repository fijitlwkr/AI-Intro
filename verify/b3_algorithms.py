"""B3: 실제 크기 L0/L1에서 팀원의 UCS와 A* 3종 등을 같은 목적함수로 비교.

상태 전이와 비용은 공통 환경을 공유한다. 규칙 구현의 독립 검증은 아니다.
CSP는 다른 사람 브랜치를 고치지 않고 등록/시간 제한/규칙 준수 검토 대상으로 남긴다.
"""
import argparse
import datetime
import json
from pathlib import Path

from agents import REGISTRY
from env.scenario import load_for
from runner.play import run_game
from runner.run import parse_seeds
from .b_common import require_clean, metadata, finish


def objective_value(row, objective):
    return row["score_cost"] if objective == "c1" else row["score_avg_time"]


def compare_case(rows, objective):
    errors = [f"{r['algorithm']}: 잘못된 행동 {r['score_wrong_actions']}건"
              for r in rows if r["score_wrong_actions"]]
    reference = next(r for r in rows if r["algorithm"] == "ucs")
    if not reference["score_success"]:
        return {"errors": errors, "compared": 0, "note": "UCS 미완료: 최적 비용 비교 보류"}
    optimum = objective_value(reference, objective)
    compared = 0
    for row in rows:
        if not row["score_success"]:
            continue
        value = objective_value(row, objective)
        if row["algorithm"] in ("astar", "idastar"):
            compared += 1
            if abs(value - optimum) > 1e-9:
                errors.append(f"{row['algorithm']} {row['params']}: 최적 목적값 불일치 {value} != {optimum}")
        elif value < optimum - 1e-9:
            errors.append(f"{row['algorithm']}: UCS보다 작은 비용: 모델/목적함수 확인 필요")
    bfs = next((r for r in rows if r["algorithm"] == "bfs" and r["score_success"]), None)
    ids = next((r for r in rows if r["algorithm"] == "ids" and r["score_success"]), None)
    if bfs and ids and len(bfs["actions"]) != len(ids["actions"]):
        errors.append("BFS와 IDS의 최소 행동 수 불일치")
    return {"errors": errors, "compared": compared, "ucs_objective_value": optimum}


def configurations(objective, iterative=False):
    configs = [("ucs", {"objective": objective})]
    configs += [("astar", {"heuristic": h, "objective": objective})
                for h in ("max_distance", "mst", "constraint")]
    configs += [("greedy", {"heuristic": "mst", "objective": objective})]
    if objective == "c1":
        configs += [("bfs", {}), ("dfs", {})]
        if iterative:
            configs += [("ids", {"memo": True})]
    if iterative:
        configs += [("idastar", {"heuristic": "mst", "objective": objective, "memo": True})]
    return configs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--presets", nargs="+", choices=("L0", "L1"), default=["L0", "L1"])
    ap.add_argument("--seeds", default="0-9")
    ap.add_argument("--objectives", nargs="+", choices=("c1", "c2"), default=["c1", "c2"])
    ap.add_argument("--include-iterative", action="store_true")
    ap.add_argument("--time-limit", type=float, default=60.0)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    require_clean()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    commit = metadata()["commit"]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    details, all_rows = [], []
    with (out / "b3_games.jsonl").open("w", encoding="utf-8") as stream:
        for preset in args.presets:
            for seed in sorted(set(parse_seeds(args.seeds))):
                scenario, _ = load_for(preset, seed)
                for objective in args.objectives:
                    rows = []
                    for index, (name, params) in enumerate(configurations(objective, args.include_iterative)):
                        row = run_game(REGISTRY[name](**params), scenario, time_limit=args.time_limit,
                                       run_id=f"{stamp}-{preset}-{seed:03d}-{objective}-{index}",
                                       params=params, git_commit=commit)
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        stream.flush()
                        rows.append(row)
                        all_rows.append(row)
                    result = compare_case(rows, objective)
                    details.append({"preset": preset, "seed": seed, "orders": len(scenario.orders),
                                    "objective": objective, **result})
                    print(f"{preset} seed={seed} {objective}: 비교 {result['compared']}, 불일치 {len(result['errors'])}", flush=True)
    incomplete = [{"algorithm": r["algorithm"], "params": r["params"], "preset": r["preset"], "seed": r["seed"],
                   "failure": r["failure"], "compute_sec": r["compute_sec"]}
                  for r in all_rows if not r["score_success"]]
    errors = sum(len(d["errors"]) for d in details)
    report = {
        "status": "fail" if errors else "conditional",
        "automated_status": "fail" if errors else ("conditional" if incomplete else "pass"),
        "games": len(all_rows), "cases": len(details), "time_limit_sec_per_game": args.time_limit,
        "optimal_cost_comparisons": sum(d["compared"] for d in details),
        "mismatches": errors, "incomplete_games": incomplete, "details": details,
        "scope": "저장된 실제 크기 L0/L1. 같은 목표함수의 성공한 UCS/A*/IDA* 비교",
        "limitations": ["공통 상태/비용 모델 공유: 규칙 명세의 독립 검증 아님",
                       "구현자가 아닌 사람의 설명-코드 대조 확인은 별도 서명 필요",
                       "CSP는 main 미등록이며 feature/csp 담당자와 수정/시험 범위 협의 필요",
                       "IDS/IDA* memo=false 실제 크기의 시간 폭발은 별도 성능 한계"],
    }
    return finish(report, out / "b3_report.json")


if __name__ == "__main__":
    raise SystemExit(main())
