"""검증 A2 교차 확인: 팀원이 올린 로그가 같은 커밋에서 다시 돌린 우리 로그와 같은 판을 만드는지 비교한다.

python -m verify.a2_crosscheck --ours runs/20261117/pairs-e79245f --theirs runs/20261117/uploaded-팀원 [--out 결과.md]

--ours, --theirs에는 .jsonl 파일이나 폴더(하위 폴더까지 모든 *.jsonl)를 여러 개 줄 수 있다.
짝짓는 기준: (알고리즘, 설정 params, 재계획, 프리셋, 시드). 짝이 있으면 점수와 행동열이 같은지 본다.
다르면 올라온 로그의 git_commit과 python_version을 같이 보여 준다. 코드가 달랐다면 다른 것이 정상일 수 있다.
우리 쪽에 같은 설정이 없는 로그는 '우리에게 없음'으로 나열한다(그 설정을 우리 커밋에서 돌려 보면 된다).
"""
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from runner import summarize as sm

COMPARE = ("score_cost", "score_avg_time", "score_success", "score_complaints", "score_expired", "score_wrong_actions")


def collect(paths):
    files = []
    for p in paths:
        p = Path(p)
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]
    rows, _ = sm.dedupe(sm.load_rows(files))
    return rows, files


def key_of(r):
    return (r["algorithm"], json.dumps(r.get("params") or {}, sort_keys=True), r["replan"], r["preset"], r["seed"])


def group_of(r):
    return key_of(r)[:4]


def label(group):
    alg, params, replan, preset = group
    p = json.loads(params)
    extra = ",".join(f"{k}={v}" for k, v in p.items())
    return f"{alg}{':' + extra if extra else ''}@{replan} {preset}"


def actions_hash(r):
    return hashlib.sha1(json.dumps(r.get("actions"), sort_keys=True).encode()).hexdigest()[:12]


def crosscheck(ours, theirs):
    mine = {key_of(r): r for r in ours}
    groups = defaultdict(list)
    for r in theirs:
        groups[group_of(r)].append(r)
    out = []
    for g, rs in sorted(groups.items()):
        item = {"group": label(g), "n_theirs": len(rs), "matched": 0, "identical": 0, "differ": 0, "missing_ours": 0,
                "differ_seeds": [], "differ_fields": defaultdict(int), "hash_mismatch": 0,
                "commits": sorted({r.get("git_commit") or "?" for r in rs}),
                "pythons": sorted({r.get("python_version") or "?" for r in rs}),
                "schemas": sorted({str(r.get("schema_version")) for r in rs})}
        for r in sorted(rs, key=lambda x: x["seed"]):
            m = mine.get(key_of(r))
            if m is None:
                item["missing_ours"] += 1
                continue
            item["matched"] += 1
            bad = [f for f in COMPARE if r.get(f) != m.get(f)]
            if r.get("actions") is not None and actions_hash(r) != actions_hash(m):
                bad.append("actions")
            if r.get("scenario_sha256") and m.get("scenario_sha256") and r["scenario_sha256"] != m["scenario_sha256"]:
                item["hash_mismatch"] += 1
                bad.append("scenario_sha256")
            if bad:
                item["differ"] += 1
                item["differ_seeds"].append(r["seed"])
                for f in bad:
                    item["differ_fields"][f] += 1
            else:
                item["identical"] += 1
        out.append(item)
    return out


def render(results, ours_files, theirs_files):
    lines = ["# 팀원 로그 교차 확인", "",
             f"- 우리 로그: {len(ours_files)}개 파일. 올라온 로그: {len(theirs_files)}개 파일.",
             "- `일치` = 같은 (알고리즘, 설정, 재계획, 프리셋, 시드)에서 점수와 행동열이 모두 같음.", "",
             "| 알고리즘 설정 | 올라온 판 | 짝 있음 | 일치 | 불일치 | 우리에게 없음 | 올라온 커밋 | Python | 스키마 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['group']} | {r['n_theirs']} | {r['matched']} | {r['identical']} | "
                     f"{'**' + str(r['differ']) + '**' if r['differ'] else 0} | {r['missing_ours']} | "
                     f"{', '.join(r['commits'])} | {', '.join(r['pythons'])} | {', '.join(r['schemas'])} |")
    bad = [r for r in results if r["differ"]]
    if bad:
        lines += ["", "## 불일치 상세", ""]
        for r in bad:
            fields = ", ".join(f"{k} {v}건" for k, v in sorted(r["differ_fields"].items()))
            lines.append(f"- {r['group']}: 시드 {r['differ_seeds'][:10]}{' 외' if len(r['differ_seeds']) > 10 else ''} / 다른 항목: {fields}")
        lines.append("- 올라온 로그의 커밋이 우리 커밋과 다르면 코드가 달라서 다를 수 있다. 같은 커밋인데 다르면 원인을 찾아야 한다.")
    miss = [r for r in results if r["missing_ours"]]
    if miss:
        lines += ["", "## 우리에게 없는 설정 (우리 커밋에서 돌려 보면 비교할 수 있음)", ""]
        lines += [f"- {r['group']}: {r['missing_ours']}판" for r in miss]
    if not bad and not miss:
        lines += ["", "모든 짝이 일치한다."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ours", nargs="+", required=True)
    ap.add_argument("--theirs", nargs="+", required=True)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    ours, of = collect(args.ours)
    theirs, tf = collect(args.theirs)
    text = render(crosscheck(ours, theirs), of, tf)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
