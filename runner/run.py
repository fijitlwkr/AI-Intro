"""알고리즘을 시나리오에 돌려 로그(JSONL, 한 판 한 줄)를 남긴다.

예)  python -m runner.run --agent random --preset L0 --seeds 0-4
     python -m runner.run --agent random --preset L2 --seeds 0-19 --replan on_complaint
로그는 logs/ 에 쌓이고 저장소에는 올라가지 않는다(.gitignore).
"""
import argparse
import importlib
import json
from datetime import datetime
from pathlib import Path

from agents import REGISTRY
from env import PRESETS, REPLAN_MODES, scenario as scenario_mod
from .play import run_game, TIME_LIMIT_SEC

ROOT = Path(__file__).resolve().parent.parent


def parse_seeds(text):
    seeds = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            seeds.extend(range(int(a), int(b) + 1))
        else:
            seeds.append(int(part))
    return seeds


def resolve_agent(name):
    if name in REGISTRY:
        return REGISTRY[name]
    if ":" in name:                                   # 예: agents.my_algo:MyAgent
        module, cls = name.split(":")
        return getattr(importlib.import_module(module), cls)
    raise SystemExit(f"알 수 없는 알고리즘 '{name}'. agents/__init__.py의 REGISTRY에 등록했는지 확인하세요: {sorted(REGISTRY)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", required=True)
    ap.add_argument("--preset", default="L2", choices=sorted(PRESETS))
    ap.add_argument("--seeds", default="0-19", help="예: 0-19 또는 0,5,7")
    ap.add_argument("--replan", default="never", choices=REPLAN_MODES)
    ap.add_argument("--time-limit", type=float, default=TIME_LIMIT_SEC)
    ap.add_argument("--out", help="로그 파일 경로 (기본: logs/<알고리즘>_<프리셋>_<시각>.jsonl)")
    args = ap.parse_args(argv)

    agent_cls = resolve_agent(args.agent)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else ROOT / "logs" / f"{args.agent}_{args.preset}_{stamp}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    generated = 0
    rows = []
    with out.open("a", encoding="utf-8") as f:
        for seed in parse_seeds(args.seeds):
            sc, from_file = scenario_mod.load_for(args.preset, seed)
            generated += 0 if from_file else 1
            agent = agent_cls(replan=args.replan)
            line = run_game(agent, sc, args.time_limit, run_id=f"{stamp}-{args.agent}-{args.preset}-{seed:03d}")
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            rows.append(line)

    ok = sum(1 for r in rows if r["score_success"])
    print(f"{len(rows)}판 완료, 성공 {ok}판. 로그: {out}")
    if generated:
        print(f"주의: 시나리오 파일이 없어 {generated}판은 즉석에서 만들었습니다. "
              "python -m runner.make_scenarios 로 파일을 만들어 모두 같은 판을 쓰세요.")


if __name__ == "__main__":
    main()
