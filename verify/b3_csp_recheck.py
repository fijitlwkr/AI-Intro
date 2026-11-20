"""CSP 반례와 수정 제안을 재검증한다. 원본/다른 팀원 브랜치는 수정하지 않는다.

python -m verify.b3_csp_recheck --out-dir logs/runs/20261117/b/csp_candidate
기본: L0~L3 각 100판 + L2 재계획 2모드/FC-off 각 10판 = 430판.
"""
import argparse
import datetime
import json
from pathlib import Path

from env import DeliveryEnv, Scenario
from env.scenario import load_for
from runner.play import run_game
from runner.run import parse_seeds
from runner.summarize import summarize
from .b_common import require_clean, metadata, finish
from .csp_candidate import CSPCandidateAgent
from .fixtures.csp_d9fb289 import CSPAgent


def counterexample():
    import random
    sc = Scenario("csp-counterexample", "L1", 0, (), (1, 2),
                  ((0, 0), (1, 1), (2, 4)), ())
    env = DeliveryEnv(sc)
    env.state = env.state._replace(status=(0, 1, 1))
    obs = env.state
    result = {}
    for label, cls in (("original", CSPAgent), ("candidate", CSPCandidateAgent)):
        agent = cls()
        agent.reset(env, random.Random(0))
        action = agent.choose_action(obs)
        result[label] = {"action": int(action), "legal": action in env.legal_actions(obs)}
    return {"status": "pass" if not result["original"]["legal"] and result["candidate"]["legal"] else "fail",
            "loaded_menus": ["피자", "탕수육"], "current_restaurant": "김치", **result}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", default="0-99")
    ap.add_argument("--replan-seeds", default="0-9")
    ap.add_argument("--time-limit", type=float, default=60.0)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    require_clean()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    commit = metadata()["commit"]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    seeds = sorted(set(parse_seeds(args.seeds)))
    extra_seeds = sorted(set(parse_seeds(args.replan_seeds)))
    configs = [(p, "never", True, seeds) for p in ("L0", "L1", "L2", "L3")]
    configs += [("L2", m, True, extra_seeds) for m in ("on_complaint", "every_step")]
    configs += [("L2", "never", False, extra_seeds)]
    all_rows, errors = [], []
    for preset, mode, fc, seed_list in configs:
        label = f"{preset}_{mode}_fc{int(fc)}"
        with (out / f"{label}.jsonl").open("w", encoding="utf-8") as stream:
            for seed in seed_list:
                scenario, _ = load_for(preset, seed)
                try:
                    row = run_game(CSPCandidateAgent(replan=mode, fc=fc), scenario,
                                   time_limit=args.time_limit, run_id=f"{stamp}-{label}-{seed:03d}",
                                   params={"fc": fc}, git_commit=commit)
                except RuntimeError as exc:
                    errors.append({"config": label, "seed": seed, "error": str(exc)})
                    continue
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                all_rows.append(row)
                if not row["score_success"] or row["score_wrong_actions"]:
                    errors.append({"config": label, "seed": seed, "failure": row["failure"],
                                   "wrong_actions": row["score_wrong_actions"]})
                if mode == "every_step" and row["compute_replans"] != len(row["actions"]) - 1:
                    errors.append({"config": label, "seed": seed, "error": "재계획 횟수 불일치"})
        print(f"{label}: {len(seed_list)}판 실행", flush=True)
    reproduction = counterexample()
    report = {
        "status": "fail" if errors or reproduction["status"] != "pass" else "pass",
        "source_commit": "d9fb2898a8c8c786bf1e32bb8a3c7e9aca8cb73e",
        "candidate_only": True, "attempted_games": sum(len(c[3]) for c in configs),
        "logged_games": len(all_rows), "successful_games": sum(r["score_success"] for r in all_rows),
        "wrong_actions": sum(r["score_wrong_actions"] for r in all_rows),
        "timeouts": sum(r["failure"] == "timeout" for r in all_rows),
        "time_limit_sec_per_game": args.time_limit, "counterexample": reproduction,
        "summary": summarize(all_rows), "errors": errors,
        "scope": "부분 적재 반례와 제안 구현의 실행 안전성. 원본 전체 성능/최적성 검증이 아님",
        "remaining": ["CSP 담당자와 수정안 통합 여부 결정", "상세 명세 기반 독립 시뮬레이터는 별도 진행"],
    }
    return finish(report, out / "csp_recheck.json")


if __name__ == "__main__":
    raise SystemExit(main())
