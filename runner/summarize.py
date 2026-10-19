"""로그(JSONL)를 요약한다. Notion 비교표에 옮길 값과 알고리즘 페이지에 적을 전체 지표를 뽑는 용도다.

예)  python -m runner.summarize                          # logs/ 안의 모든 로그: 공통 지표 표 + 특성지표 표
     python -m runner.summarize logs/random_L2_*.jsonl   # 일부만
     python -m runner.summarize --notion                 # Notion 비교표 열 순서로 (붙여넣기용)
     python -m runner.summarize --csv summary.csv        # 표를 CSV로도 저장 (--notion과 같이 쓰면 그 표를 저장)
     python -m runner.summarize --vs astar ucs --field compute_nodes_expanded
                                                         # A*가 UCS보다 노드를 몇 % 줄였나(절감률). 같은 시드끼리 짝지어 계산
     python -m runner.summarize --vs "csp:forward_checking=true" "csp:forward_checking=false" --field compute_backtracks

같은 (알고리즘, 설정, 프리셋, 재계획, 시드)가 여러 번 있으면 가장 나중 실행만 쓴다(중복으로 세지 않는다).
프리셋 값([초안] 값 등)이 다르게 돌린 로그는 한 줄로 합치지 않고 따로 보여 준다.
"""
import argparse
import csv
import glob
import json
import math
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PRESET = "L2"
OPTIMAL_GAP_PRESETS = ("L0", "L1")     # 최적격차는 항의가 없는 설정에서만 의미가 있다

# 특성지표 표의 열: (표시 이름, 요약 키)
TRAIT_COLUMNS = [
    ("노드수", "nodes_expanded"), ("메모리", "mem_states"), ("허용성", "h_violations"),
    ("재계획횟수", "replans"), ("탐색깊이", "depth"), ("백트랙수", "backtracks"),
    ("규칙수", "rules"), ("계획길이", "plan_len"), ("위반율", "wrong_rate"),
    ("최악성능", "worst10"), ("최적격차", "opt_gap"),
]
# 로그 필드 -> 요약 키 (null은 평균에서 제외)
TRAIT_FIELDS = {
    "nodes_expanded": "compute_nodes_expanded", "mem_states": "compute_mem_states",
    "h_violations": "compute_h_violations", "replans": "compute_replans", "depth": "compute_depth",
    "backtracks": "compute_backtracks", "rules": "compute_rules", "plan_len": "compute_plan_len",
}


# ---------------------------------------------------------------- 읽기와 묶기
def load_rows(paths):
    rows = []
    for p in sorted(paths):
        for n, line in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                row["_src"] = f"{Path(p).name}:{n}"
                rows.append(row)
    return rows


def _params_key(row):
    return json.dumps(row.get("params") or {}, sort_keys=True, ensure_ascii=False)


def _settings_key(row):
    """프리셋 값의 지문. 로그에 기록이 없으면(v1) None."""
    pp = row.get("preset_params")
    if not pp:
        return None
    return json.dumps({k: v for k, v in pp.items() if k != "name"}, sort_keys=True)


def dedupe(rows):
    """같은 (알고리즘, 설정, 프리셋, 재계획, 시드)는 run_id가 가장 나중인 것만 남긴다."""
    latest = {}
    for r in rows:
        key = (r["algorithm"], _params_key(r), r["preset"], r["replan"], r["seed"])
        if key not in latest or (r.get("run_id") or "") >= (latest[key].get("run_id") or ""):
            latest[key] = r
    return list(latest.values()), len(rows) - len(latest)


def group_rows(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["algorithm"], _params_key(r), r["preset"], r["replan"], _settings_key(r))].append(r)
    return groups


def label_of(algorithm, params_key, replan):
    parts = [f"{k}={v}" for k, v in json.loads(params_key).items()]
    if replan != "never":
        parts.append(f"replan={replan}")
    return algorithm + (f" ({', '.join(parts)})" if parts else "")


# ---------------------------------------------------------------- 계산
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def worst10(costs):
    """총비용이 나쁜 쪽 10% 판의 평균 (최소 1판)."""
    k = max(1, math.ceil(len(costs) * 0.1))
    return st.mean(sorted(costs, reverse=True)[:k])


def _group_order(item):
    (alg, pkey, preset, replan, skey), _ = item
    return (alg, preset, pkey != "{}", pkey, replan, str(skey))     # 설정 없는 기본 줄이 먼저


def summarize(rows):
    out = []
    for (alg, pkey, preset, replan, skey), rs in sorted(group_rows(rows).items(), key=_group_order):
        arrived = sum(r["score_complaints"] for r in rs)
        miss_games = [r["score_complaint_miss"] for r in rs if r["score_complaint_miss"] is not None]
        actions = sum(len(r["actions"]) for r in rs)
        s = {
            "algorithm": alg, "params_key": pkey, "label": label_of(alg, pkey, replan),
            "preset": preset, "replan": replan, "settings_key": skey, "games": len(rs),
            "seeds": sorted(r["seed"] for r in rs),
            "success_rate": sum(1 for r in rs if r["score_success"]) / len(rs),
            "cost_mean": st.mean(r["score_cost"] for r in rs),
            "cost_min": min(r["score_cost"] for r in rs), "cost_max": max(r["score_cost"] for r in rs),
            "avg_time_mean": st.mean(r["score_avg_time"] for r in rs),
            "miss_pooled": (sum(r["score_expired"] for r in rs) / arrived) if arrived else None,
            "miss_per_game": _mean(miss_games),
            "complaints_per_game": arrived / len(rs),
            "compute_sec_mean": st.mean(r["compute_sec"] for r in rs),
            "timeouts": sum(1 for r in rs if r.get("failure") == "timeout"),
            "wrong_rate": (sum(r["score_wrong_actions"] for r in rs) / actions) if actions else None,
            "worst10": worst10([r["score_cost"] for r in rs]),
            "opt_gap": None, "opt_gap_n": 0,
            "last_run": max((r.get("run_id") or "") for r in rs),
            "commits": sorted({r["git_commit"] for r in rs if r.get("git_commit")}),
        }
        for key, field in TRAIT_FIELDS.items():
            s[key] = _mean([r.get(field) for r in rs])
        out.append(s)
    return out


def add_optimal_gap(summary, rows, reference):
    """같은 프리셋·시드에서 기준 알고리즘(성공한 판)보다 총비용이 몇 % 큰지의 평균. L0·L1에서만."""
    ref = {(r["preset"], r["seed"]): r["score_cost"]
           for r in rows if r["algorithm"] == reference and r["score_success"] and not r.get("params")}
    if not ref:
        return False
    by_group = group_rows(rows)
    for s in summary:
        if s["preset"] not in OPTIMAL_GAP_PRESETS:
            continue
        rs = by_group[(s["algorithm"], s["params_key"], s["preset"], s["replan"], s["settings_key"])]
        gaps = [(r["score_cost"] - ref[(r["preset"], r["seed"])]) / ref[(r["preset"], r["seed"])]
                for r in rs if (r["preset"], r["seed"]) in ref and ref[(r["preset"], r["seed"])] > 0]
        if gaps:
            s["opt_gap"], s["opt_gap_n"] = st.mean(gaps), len(gaps)
    return True


def parse_spec(text):
    """'astar' 또는 'csp:forward_checking=true,depth=3' -> (알고리즘, {설정})."""
    name, _, rest = text.partition(":")
    params = {}
    for item in filter(None, rest.split(",")):
        k, _, v = item.partition("=")
        low = v.lower()
        params[k] = (low == "true") if low in ("true", "false") else (int(v) if re.fullmatch(r"-?\d+", v) else v)
    return name, params


def vs_report(rows, spec_a, spec_b, field):
    """A와 B를 같은 (프리셋, 시드)끼리 짝지어 field 값이 A에서 얼마나 줄었는지 (1 - 합A/합B)."""
    def pick(spec):
        name, params = parse_spec(spec)
        return {(r["preset"], r["seed"]): r.get(field) for r in rows
                if r["algorithm"] == name and all((r.get("params") or {}).get(k) == v for k, v in params.items())
                and r.get(field) is not None}
    a, b = pick(spec_a), pick(spec_b)
    pairs = sorted(set(a) & set(b))
    if not pairs:
        return f"--vs: '{spec_a}'와 '{spec_b}'가 같은 (프리셋, 시드)로 돌린 로그가 없어 계산할 수 없습니다."
    sa, sb = sum(a[p] for p in pairs), sum(b[p] for p in pairs)
    red = (1 - sa / sb) if sb else None
    return (f"{field}: {spec_a} 평균 {sa/len(pairs):.2f}, {spec_b} 평균 {sb/len(pairs):.2f} "
            f"(짝지은 판 {len(pairs)}) -> {spec_a}가 {spec_b}보다 "
            + (f"{red:.1%} 줄임" if red is not None and red >= 0 else (f"{-red:.1%} 늘림" if red is not None else "계산 불가")))


def warnings_for(rows, summary, n_versions):
    notes = []
    if n_versions > 1:
        notes.append(f"로그 형식 버전이 섞여 있습니다 {sorted(map(str, n_versions_set(rows)))}. 이전 버전 로그는 설정 기록이 없습니다.")
    by_alg = defaultdict(list)
    for s in summary:
        by_alg[(s["algorithm"], s["params_key"], s["preset"], s["replan"])].append(s)
    for key, ss in by_alg.items():
        if len(ss) > 1:
            notes.append(f"{label_of(key[0], key[1], key[3])} {key[2]}: 프리셋 값이 다른 로그가 섞여 있어 따로 보여 줍니다. "
                         "[초안] 값이 바뀐 뒤라면 최신 설정으로 다시 돌린 줄만 쓰세요.")
    seed_sets = defaultdict(set)
    for s in summary:
        seed_sets[s["preset"]].add(tuple(s["seeds"]))
    for preset, sets in seed_sets.items():
        if len(sets) > 1:
            notes.append(f"{preset}: 알고리즘마다 돌린 시드가 다릅니다. 비교하려면 같은 시드로 돌려야 합니다.")
    for s in summary:
        if len(s["commits"]) > 1:
            notes.append(f"{s['label']} {s['preset']}: 서로 다른 코드 버전({', '.join(s['commits'])})의 로그가 섞여 있습니다.")
        if any(c.endswith("+dirty") for c in s["commits"]):
            notes.append(f"{s['label']} {s['preset']}: 커밋하지 않은 변경이 있는 상태에서 돌린 로그가 있습니다 (+dirty).")
    return notes


def n_versions_set(rows):
    return {r.get("schema_version") for r in rows}


# ---------------------------------------------------------------- 출력
def _fmt(v, nd=3):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def _md(head, body):
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def common_table(summary):
    head = ["알고리즘", "프리셋", "판수", "성공률", "총비용(평균)", "총비용(최소~최대)", "평균배달시간",
            "항의초과율", "판당 항의", "계산시간(초/판)", "시간초과"]
    body = [[s["label"], s["preset"], s["games"], f"{s['success_rate']:.0%}", _fmt(s["cost_mean"], 1),
             f"{s['cost_min']}~{s['cost_max']}", _fmt(s["avg_time_mean"], 1), _fmt(s["miss_pooled"]),
             _fmt(s["complaints_per_game"], 1), _fmt(s["compute_sec_mean"], 5), s["timeouts"]] for s in summary]
    return head, body


def trait_table(summary):
    cols = [(name, key) for name, key in TRAIT_COLUMNS if any(s.get(key) is not None for s in summary)]
    if not cols:
        return None
    head = ["알고리즘", "프리셋"] + [n for n, _ in cols]
    body = []
    for s in summary:
        row = [s["label"], s["preset"]]
        for name, key in cols:
            v = s.get(key)
            if key == "wrong_rate":
                row.append("-" if v is None else f"{v:.1%}")
            elif key == "opt_gap":
                row.append("-" if v is None else f"{v:+.1%} (n={s['opt_gap_n']})")
            else:
                row.append(_fmt(v, 1))
        body.append(row)
    return head, body


NOTION_HEAD = ["알고리즘", "총비용", "평균배달시간", "성공률", "항의초과율", "계산시간(초)", "측정조건"]


def notion_table(summary):
    """Notion 비교표의 열 순서와 형식. 성공률·항의초과율은 퍼센트 칸이라 %로 쓴다. 해당 없는 값은 비운다."""
    body = []
    for s in summary:
        d = f"{s['last_run'][:4]}-{s['last_run'][4:6]}-{s['last_run'][6:8]}" if re.match(r"\d{8}", s["last_run"]) else date.today().isoformat()
        cond = f"시드 {s['games']}, {d}" + ("" if s["preset"] == DEFAULT_PRESET else f", {s['preset']}")
        miss = "" if s["miss_pooled"] is None else f"{s['miss_pooled']:.1%}"
        body.append([s["label"], f"{s['cost_mean']:.1f}", f"{s['avg_time_mean']:.1f}", f"{s['success_rate']:.1%}",
                     miss, f"{s['compute_sec_mean']:.4f}", cond])
    return NOTION_HEAD, body


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="로그 파일 (기본: logs/*.jsonl)")
    ap.add_argument("--preset", help="이 프리셋만 요약")
    ap.add_argument("--notion", action="store_true", help="Notion 비교표 열 순서로 출력")
    ap.add_argument("--csv", help="표를 CSV로 저장할 경로")
    ap.add_argument("--reference", default="ucs", help="최적격차의 기준 알고리즘 이름 (기본 ucs)")
    ap.add_argument("--vs", nargs=2, metavar=("A", "B"), help="두 알고리즘(또는 설정)의 지표를 같은 시드끼리 비교")
    ap.add_argument("--field", default="compute_nodes_expanded", help="--vs로 비교할 로그 필드")
    args = ap.parse_args(argv)

    paths = [p for pat in args.files for p in glob.glob(pat)] if args.files else glob.glob(str(ROOT / "logs" / "*.jsonl"))
    if not paths:
        raise SystemExit("읽을 로그가 없습니다. 먼저 python -m runner.run 으로 로그를 만드세요.")
    rows = load_rows(paths)
    if args.preset:
        rows = [r for r in rows if r["preset"] == args.preset]
    nver = len(n_versions_set(rows))
    rows, dropped = dedupe(rows)
    summary = summarize(rows)
    has_ref = add_optimal_gap(summary, rows, args.reference)

    if args.notion:
        head, body = notion_table(summary)
        print(_md(head, body))
    else:
        head, body = common_table(summary)
        print("## 공통 지표\n")
        print(_md(head, body))
        traits = trait_table(summary)
        if traits:
            print("\n## 특성지표\n")
            print(_md(*traits))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(body)
        print(f"\nCSV 저장: {args.csv}")

    if args.vs:
        print("\n## 비교 (--vs)\n")
        print(vs_report(rows, args.vs[0], args.vs[1], args.field))

    print(f"\n로그 {len(paths)}개, {len(rows)}판 사용" + (f" (같은 시드의 이전 실행 {dropped}판은 제외)" if dropped else ""))
    notes = warnings_for(rows, summary, nver)
    if not has_ref and any(s["preset"] in OPTIMAL_GAP_PRESETS for s in summary):
        notes.append(f"최적격차: 기준 알고리즘 '{args.reference}'의 성공한 로그가 없어 계산하지 않았습니다 (L0·L1에서만 계산).")
    for n in notes:
        print("주의:", n)
    print("평균배달시간은 끝내지 못한 주문의 완료 시각을 H(500)로 계산한 값입니다. "
          "항의초과율은 초과 건수 / 발생 건수입니다.")


if __name__ == "__main__":
    main()
