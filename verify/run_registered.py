"""검증 A2: 사전 확정 비교쌍 7개에 필요한 알고리즘을 같은 커밋에서 한꺼번에 돌린다.

python -m verify.run_registered --out runs/20261118/pairs [--preset L2] [--seeds 0-99] [--dry-run]

- 커밋하지 않은 변경이 있으면 멈춘다(로그에 +dirty가 남기 때문). 꼭 필요하면 --allow-dirty.
- out 폴더에 알고리즘별 로그, manifest.json(커밋, Python, 시각), env.json(CPU, RAM, OS)을 남긴다.
- CPU와 RAM은 Linux에서 자동으로 읽는다. 다른 OS나 직접 적으려면 --cpu "..." --ram-gb 16 을 쓴다.
"""
import argparse
import datetime
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = [  # (파일 이름 앞부분, runner.run 인자)
    ("astar_never", ["--agent", "astar", "--replan", "never"]),
    ("astar_on_complaint", ["--agent", "astar", "--replan", "on_complaint"]),
    ("rule", ["--agent", "rule"]),
    ("logic", ["--agent", "logic"]),
    ("greedy", ["--agent", "greedy"]),
    ("ucs", ["--agent", "ucs"]),
    ("dfs", ["--agent", "dfs"]),
]


def git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def is_dirty():
    return git("status", "--porcelain") != ""


def hardware(cpu=None, ram_gb=None):
    info = {"cpu_model": cpu, "ram_gb": ram_gb, "logical_cores": os.cpu_count(), "os": platform.platform(),
            "python": platform.python_version()}
    try:
        if cpu is None:
            info["cpu_model"] = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
        if ram_gb is None:
            kb = int(next(l for l in open("/proc/meminfo") if l.startswith("MemTotal")).split()[1])
            info["ram_gb"] = round(kb / 1024 / 1024, 1)
    except (OSError, StopIteration):
        pass
    return info


def commands(out, preset, seeds):
    return [([sys.executable, "-m", "runner.run", *args, "--preset", preset, "--seeds", seeds,
              "--out", str(Path(out) / f"{name}_{preset}_s{seeds.replace('-', '-')}.jsonl")], name) for name, args in CONFIGS]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preset", default="L2")
    ap.add_argument("--seeds", default="0-99")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--cpu")
    ap.add_argument("--ram-gb", type=float)
    args = ap.parse_args(argv)

    cmds = commands(args.out, args.preset, args.seeds)
    if args.dry_run:
        for c, _ in cmds:
            print(" ".join(c))
        return 0
    if is_dirty() and not args.allow_dirty:
        print("커밋하지 않은 변경이 있어 멈춥니다. 커밋하거나 --allow-dirty를 쓰세요(로그에 +dirty가 남습니다).")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for c, name in cmds:
        print(f"== {name}")
        subprocess.run(c, cwd=ROOT, check=True)
    manifest = {"commit": git("rev-parse", "--short", "HEAD"), "preset": args.preset, "seeds": args.seeds,
                "python": platform.python_version(), "dirty": is_dirty(),
                "recorded_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                "files": sorted(p.name for p in out.glob("*.jsonl"))}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "env.json").write_text(json.dumps(hardware(args.cpu, args.ram_gb), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: {out} (커밋 {manifest['commit']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
