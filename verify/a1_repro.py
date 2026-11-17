"""검증 A1 ② 재현 동일성: 같은 (알고리즘, 프리셋, 시드)를 조건을 바꿔 돌려 행동열·점수 해시를 모은다.

python -m verify.a1_repro run --out base.json [--order forward|reverse] [--agents a,b] [--presets L0,L1] [--seeds 0-19]
python -m verify.a1_repro compare base.json other1.json other2.json ...

핵심 해시(core) = 행동열, score_* 전부, failure, 시나리오 해시. 계산시간은 넣지 않는다.
보조 해시(aux) = 노드 수와 compute_* 특성 지표. 조건에 따라 달라지는지 따로 본다.
"""
import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

from agents import REGISTRY
from env import REPORT_FIELDS
from env.scenario import load_for
from runner.play import run_game

DEFAULT_AGENTS = "random,rule,logic,greedy,astar,ucs,bfs,dfs"


def parse_seeds(text):
    out = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(part))
    return out


def parse_agent(spec):
    """'ids:memo=true' -> (라벨, 클래스, params)"""
    name, _, rest = spec.partition(":")
    params = {}
    for item in filter(None, rest.split(";")):
        k, v = item.split("=", 1)
        params[k] = {"true": True, "false": False}.get(v.lower(), v)
        if isinstance(params[k], str):
            for cast in (int, float):
                try:
                    params[k] = cast(v)
                    break
                except ValueError:
                    pass
    return spec, REGISTRY[name], params


def digest(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def cmd_run(args):
    agents = [parse_agent(a) for a in args.agents.split(",")]
    presets = args.presets.split(",")
    seeds = parse_seeds(args.seeds)
    if args.order == "reverse":
        agents, presets, seeds = agents[::-1], presets[::-1], seeds[::-1]
    aux_fields = ["compute_nodes_expanded", "compute_nodes_generated"] + [f for _, f, _ in REPORT_FIELDS.values()]
    games = {}
    for label, cls, params in agents:
        for preset in presets:
            for seed in seeds:
                sc, _ = load_for(preset, seed)
                row = run_game(cls(**params), sc, params=params)
                core = {"actions": row["actions"], "failure": row["failure"], "sha": row["scenario_sha256"],
                        **{k: v for k, v in row.items() if k.startswith("score_")}}
                games[f"{label}|{preset}|{seed}"] = {"core": digest(core), "aux": digest({k: row.get(k) for k in aux_fields}),
                                                     "failure": row["failure"]}
    out = {"python": platform.python_version(), "platform": platform.platform(), "order": args.order,
           "n_games": len(games), "games": games}
    Path(args.out).write_text(json.dumps(out), encoding="utf-8")
    print(f"{len(games)}판 기록: {args.out} (python {out['python']}, order={args.order})")


def cmd_compare(args):
    base = json.loads(Path(args.files[0]).read_text())
    print(f"기준: {args.files[0]} (python {base['python']}, {base['n_games']}판)")
    bad_total = 0
    for f in args.files[1:]:
        other = json.loads(Path(f).read_text())
        keys = sorted(set(base["games"]) | set(other["games"]))
        missing = [k for k in keys if k not in base["games"] or k not in other["games"]]
        core_diff = [k for k in keys if k not in missing and base["games"][k]["core"] != other["games"][k]["core"]]
        aux_diff = [k for k in keys if k not in missing and base["games"][k]["aux"] != other["games"][k]["aux"]]
        fails = sum(1 for k in other["games"] if other["games"][k]["failure"])
        print(f"- {f}: python {other['python']}, order={other['order']}, {other['n_games']}판, 실패(timeout 등) {fails}판 | "
              f"핵심 불일치 {len(core_diff)}건, 보조 불일치 {len(aux_diff)}건, 짝 없음 {len(missing)}건")
        for k in core_diff[:10]:
            print("    핵심:", k)
        for k in aux_diff[:5]:
            print("    보조:", k)
        bad_total += len(core_diff) + len(missing)
    return 1 if bad_total else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--order", default="forward", choices=["forward", "reverse"])
    r.add_argument("--agents", default=DEFAULT_AGENTS)
    r.add_argument("--presets", default="L0,L1,L2,L3")
    r.add_argument("--seeds", default="0-19")
    c = sub.add_parser("compare")
    c.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    return cmd_run(args) if args.cmd == "run" else cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
