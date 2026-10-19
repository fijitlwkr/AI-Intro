"""로그(JSONL)를 알고리즘 x 프리셋 x 재계획 설정별로 요약한다. Notion 표에 옮길 값을 뽑는 용도다.

예)  python -m runner.summarize                         # logs/ 안의 모든 로그
     python -m runner.summarize logs/random_L2_*.jsonl  # 일부만
     python -m runner.summarize --csv summary.csv       # CSV로도 저장

같은 (알고리즘, 프리셋, 재계획, 시드)가 여러 번 있으면 가장 나중 실행만 쓴다(중복으로 세지 않는다).
"""
import argparse
import csv
import glob
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLUMNS = [
    "algorithm", "preset", "replan", "games", "success_rate",
    "cost_mean", "cost_min", "cost_max", "avg_time_mean",
    "complaint_miss_mean", "complaint_miss_pooled", "complaints_per_game",
    "compute_sec_mean", "nodes_expanded_mean", "timeouts",
]


def load_rows(paths):
    rows = []
    for p in sorted(paths):
        for n, line in enumerate(Path(p).read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_src"] = f"{Path(p).name}:{n}"
            rows.append(row)
    return rows


def dedupe(rows):
    """같은 (알고리즘, 프리셋, 재계획, 시드)는 run_id가 가장 나중인 것만 남긴다."""
    latest = {}
    for r in rows:
        key = (r["algorithm"], r["preset"], r["replan"], r["seed"])
        if key not in latest or (r.get("run_id") or "") >= (latest[key].get("run_id") or ""):
            latest[key] = r
    return list(latest.values()), len(rows) - len(latest)


def _mean(xs):
    return st.mean(xs) if xs else None


def summarize(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["algorithm"], r["preset"], r["replan"])].append(r)
    out = []
    for (alg, preset, replan), rs in sorted(groups.items()):
        miss = [r["score_complaint_miss"] for r in rs if r["score_complaint_miss"] is not None]
        arrived = sum(r["score_complaints"] for r in rs)
        nodes = [r["compute_nodes_expanded"] for r in rs if r["compute_nodes_expanded"] is not None]
        out.append({
            "algorithm": alg, "preset": preset, "replan": replan, "games": len(rs),
            "success_rate": sum(1 for r in rs if r["score_success"]) / len(rs),
            "cost_mean": st.mean(r["score_cost"] for r in rs),
            "cost_min": min(r["score_cost"] for r in rs),
            "cost_max": max(r["score_cost"] for r in rs),
            "avg_time_mean": st.mean(r["score_avg_time"] for r in rs),
            "complaint_miss_mean": _mean(miss),
            "complaint_miss_pooled": (sum(r["score_expired"] for r in rs) / arrived) if arrived else None,
            "complaints_per_game": arrived / len(rs),
            "compute_sec_mean": st.mean(r["compute_sec"] for r in rs),
            "nodes_expanded_mean": _mean(nodes),
            "timeouts": sum(1 for r in rs if r.get("failure") == "timeout"),
        })
    return out


def _fmt(v, nd=3):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render_table(summary):
    head = ["알고리즘", "프리셋", "재계획", "판수", "성공률", "총비용(평균)", "총비용(최소~최대)",
            "평균배달시간", "항의초과율(판 평균)", "항의초과율(전체)", "판당 항의", "계산시간(초/판)", "노드(expanded)", "시간초과"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for s in summary:
        cells = [
            s["algorithm"], s["preset"], s["replan"], s["games"], f"{s['success_rate']:.0%}",
            _fmt(s["cost_mean"], 1), f"{s['cost_min']}~{s['cost_max']}", _fmt(s["avg_time_mean"], 1),
            _fmt(s["complaint_miss_mean"]), _fmt(s["complaint_miss_pooled"]), _fmt(s["complaints_per_game"], 1),
            _fmt(s["compute_sec_mean"], 5), _fmt(s["nodes_expanded_mean"], 1), s["timeouts"],
        ]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="로그 파일 (기본: logs/*.jsonl)")
    ap.add_argument("--csv", help="요약을 CSV로도 저장할 경로")
    args = ap.parse_args(argv)

    paths = [p for pat in args.files for p in glob.glob(pat)] if args.files else glob.glob(str(ROOT / "logs" / "*.jsonl"))
    if not paths:
        raise SystemExit("읽을 로그가 없습니다. 먼저 python -m runner.run 으로 로그를 만드세요.")
    rows = load_rows(paths)
    versions = {r.get("schema_version") for r in rows}
    if len(versions) > 1:
        print(f"주의: 로그 형식 버전이 섞여 있습니다 {sorted(map(str, versions))}", file=sys.stderr)
    rows, dropped = dedupe(rows)
    summary = summarize(rows)
    print(render_table(summary))
    print(f"\n로그 {len(paths)}개, {len(rows)}판 사용" + (f" (같은 시드의 이전 실행 {dropped}판은 제외)" if dropped else ""))
    print("항의초과율: '판 평균'은 항의가 나온 판들의 비율 평균, '전체'는 초과 건수 / 발생 건수. 못 끝낸 주문은 완료 시각을 H로 계산한 값입니다.")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(summary)
        print(f"CSV 저장: {args.csv}")


if __name__ == "__main__":
    main()
