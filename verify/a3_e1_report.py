"""검증 A3 ③: E1 특화 시나리오 결과표. 로그(jsonl)를 읽어 에이전트별 한 줄로 보여 준다.

python -m verify.a3_e1_report <로그 폴더 또는 파일>... [--out report.md]
평균표에 섞지 않는다. 한 판의 결과를 사전 기대(verify/a3_e1_expectations.json)와 맞춰 보는 용도다.
"""
import argparse
import json
from pathlib import Path


def read(paths):
    rows = []
    for p in map(Path, paths):
        for f in sorted(p.rglob("*.jsonl")) if p.is_dir() else [p]:
            rows += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if r.get("preset") == "E1" and r.get("seed") == 0]


def label(r):
    extra = ",".join(f"{k}={v}" for k, v in sorted((r.get("params") or {}).items()))
    return f"{r['algorithm']}{'(' + extra + ')' if extra else ''}@{r['replan']}"


def render(rows):
    out = ["| 에이전트 | 성공 | 총비용 | 평균배달시간 | 총시간 | 항의 수 | 초과 | 잘못된 행동 | 실패 사유 | 커밋 |", "|---|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in sorted(rows, key=label):
        out.append(f"| {label(r)} | {'예' if r['score_success'] else '아니오'} | {r['score_cost']} | {r['score_avg_time']:.2f} | "
                   f"{r['score_total_time']} | {r['score_complaints']} | {r['score_expired']} | {r['score_wrong_actions']} | "
                   f"{r.get('failure') or '-'} | {str(r.get('git_commit'))[:7]} |")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    text = render(read(a.logs))
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
