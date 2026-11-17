"""B1-b: choose_action 누적 시간의 계측 교차 검사와 5회 반복/캐시/순서 진단.

python -m verify.b1_timing --out logs/runs/b/b1_timing.json
타이밍 계측 래퍼 자체의 오버헤드가 포함되므로 실제 성능표와 분리해 사용한다.
"""
import argparse
import statistics
import time

from agents import REGISTRY
from agents.rule_agent import _DIST_CACHE
from env.scenario import load_for
from runner.play import run_game
from runner.run import parse_seeds, parse_params
from .b_common import require_clean, finish


def measured_game(name, params, scenario):
    agent = REGISTRY[name](**params)
    original = agent.choose_action
    inside_ns = 0

    def measured(obs):
        nonlocal inside_ns
        started = time.perf_counter_ns()
        try:
            return original(obs)
        finally:
            inside_ns += time.perf_counter_ns() - started

    agent.choose_action = measured
    row = run_game(agent, scenario)
    external = inside_ns / 1e9
    difference = abs(row["compute_sec"] - external)
    tolerance = max(external * .01, .00005)
    return {"seed": scenario.seed, "logged_sec": row["compute_sec"], "wrapped_sec": external,
            "difference_sec": difference, "tolerance_sec": tolerance,
            "within_tolerance": difference <= tolerance, "success": row["score_success"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent", choices=sorted(REGISTRY), default="astar")
    ap.add_argument("--preset", default="L2")
    ap.add_argument("--seeds", default="0-9")
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--param", action="append")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.repeats < 2:
        ap.error("CV 계산에는 2회 이상이 필요합니다.")
    require_clean()
    params = parse_params(args.param or [])
    seeds = sorted(set(parse_seeds(args.seeds)))
    if not seeds:
        ap.error("한 개 이상의 시드가 필요합니다.")
    scenarios = [load_for(args.preset, seed)[0] for seed in seeds]
    # 공용 지도 최단거리 캐시만 warm-up한다. 실제 측정은 같은 시나리오로 새 에이전트를 만든다.
    measured_game(args.agent, params, scenarios[0])
    batches = []
    for repeat in range(args.repeats):
        order = scenarios if repeat % 2 == 0 else list(reversed(scenarios))
        games = [measured_game(args.agent, params, sc) for sc in order]
        batches.append({"repeat": repeat + 1, "order": "forward" if repeat % 2 == 0 else "reverse",
                        "compute_sum_sec": sum(r["logged_sec"] for r in games), "games": games})
    _DIST_CACHE.clear()
    cold = [measured_game(args.agent, params, sc) for sc in scenarios]
    totals = [b["compute_sum_sec"] for b in batches]
    mean = statistics.mean(totals)
    cv = statistics.stdev(totals) / mean if mean else None
    all_games = [r for b in batches for r in b["games"]] + cold
    failures = sum(not r["within_tolerance"] for r in all_games)
    succeeded = all(r["success"] for r in all_games)
    report = {
        "status": "fail" if failures else ("pass" if cv is not None and cv <= .10 and succeeded else "conditional"),
        "agent": args.agent, "params": params, "preset": args.preset, "seeds": seeds,
        "repeats": args.repeats, "games": len(all_games),
        "cv": cv, "cv_limit": .10, "external_tolerance_failures": failures,
        "all_games_successful": succeeded,
        "definition": "runner의 compute_sec는 choose_action에 소비한 시간의 합. reset/환경 step/로그 I/O 제외",
        "external_method": "choose_action 내부에 perf_counter_ns 래퍼를 넣고 외부 runner 시간과 비교",
        "tolerance": "판당 상대 1% 또는 절대 0.05ms 중 큰 값",
        "warm_batch_mean_sec": mean, "cold_batch_sec": sum(r["logged_sec"] for r in cold),
        "order_means_sec": {name: statistics.mean(b["compute_sum_sec"] for b in batches if b["order"] == name)
                            for name in ("forward", "reverse") if any(b["order"] == name for b in batches)},
        "limitations": ["계측 래퍼가 오버헤드를 추가하므로 성능 비교표에 섞지 않음",
                       "순서/캐시 차이는 기술 통계이며 독립 반복의 인과 효과로 해석하지 않음",
                       "전원/절전/백그라운드 부하 통제 여부는 사람이 확인해야 함"],
        "details": batches, "cold_details": cold,
    }
    return finish(report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())

