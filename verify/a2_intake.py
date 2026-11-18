"""팀원 로그 사전 점검: 교차 확인(a2_crosscheck) 전에 받은 로그를 훑어 문제를 먼저 찾는다.

python -m verify.a2_intake 받은폴더 [더_받은폴더 ...] [--preset L2] [--seeds 0-99] [--out report.md]

폴더는 하위 폴더까지 읽는다. 로그를 고치거나 합치지 않고, 읽기만 한다.
무엇을 보나: 읽을 수 없는 줄, 알고리즘 설정별 판 수와 시드 누락, 같은 판의 중복과 충돌,
커밋(+dirty)·Python·플랫폼 혼재, 스키마 버전, 시나리오 해시 유무, 프리셋 값 혼재, 규칙 위반과 실패.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from runner.run import parse_seeds


def read_all(paths):
    files, rows, bad = [], [], []
    for p in map(Path, paths):
        files += sorted(p.rglob("*.jsonl")) if p.is_dir() else ([p] if p.exists() else [])
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if not isinstance(r, dict) or "algorithm" not in r or "seed" not in r:
                    raise ValueError("필수 필드 없음")
            except Exception as e:
                bad.append(f"{f.name}:{n} {e}")
                continue
            r["_src"] = f"{f.name}:{n}"
            rows.append(r)
    return files, rows, bad


def _params(r):
    return json.dumps(r.get("params") or {}, sort_keys=True, ensure_ascii=False)


def _pp(r):
    pp = r.get("preset_params")
    return json.dumps({k: v for k, v in pp.items() if k != "name"}, sort_keys=True) if pp else None


def inspect(rows, preset, seeds):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["algorithm"], _params(r), r.get("replan"), r.get("preset"))].append(r)
    out = []
    for key in sorted(groups, key=str):
        rs = groups[key]
        alg, params, replan, pre = key
        info = {"alg": alg, "params": params, "replan": replan, "preset": pre, "rows": len(rs), "issues": [], "notes": []}
        by_seed = defaultdict(list)
        for r in rs:
            by_seed[r["seed"]].append(r)
        have = set(by_seed)
        if pre == preset:
            miss = sorted(set(seeds) - have)
            extra = sorted(have - set(seeds))
            info["missing"] = miss
            if miss:
                info["issues"].append(f"시드 {len(miss)}개 없음({_ranges(miss)})")
            if extra:
                info["notes"].append(f"범위 밖 시드 {len(extra)}개")
        dup = {s: v for s, v in by_seed.items() if len(v) > 1}
        if dup:
            conflict = [s for s, v in dup.items()
                        if len({(x.get("score_cost"), json.dumps(x.get("actions"))) for x in v}) > 1]
            info["notes"].append(f"중복 판 {len(dup)}개 시드(같은 값)" if not conflict else "")
            if conflict:
                info["issues"].append(f"같은 판인데 결과가 다른 중복 {len(conflict)}개 시드({_ranges(sorted(conflict))}): 어느 쪽이 맞는지 확인 필요")
        commits = Counter(r.get("git_commit") or "기록 없음" for r in rs)
        if len(commits) > 1:
            info["issues"].append(f"커밋이 섞임: {dict(commits)}")
        if any("+dirty" in c for c in commits):
            info["issues"].append("커밋하지 않은 변경이 있는 상태에서 돌림(+dirty)")
        if len({r.get("python_version") for r in rs}) > 1:
            info["notes"].append(f"Python 버전 혼재: {sorted({str(r.get('python_version')) for r in rs})}")
        if len({_pp(r) for r in rs}) > 1:
            info["issues"].append("프리셋 값(n, q, T, P 등)이 섞임")
        if sum(1 for r in rs if not r.get("scenario_sha256")):
            info["notes"].append(f"시나리오 해시 없음 {sum(1 for r in rs if not r.get('scenario_sha256'))}판(v3 이전 로그)")
        wrong = sum(1 for r in rs if r.get("score_wrong_actions"))
        fail = sum(1 for r in rs if r.get("score_success") is False)
        if wrong:
            info["issues"].append(f"잘못된 행동이 있는 판 {wrong}개")
        info["fail"] = fail
        info["commits"], info["python"], info["platform"] = dict(commits), sorted({str(r.get("python_version")) for r in rs}), sorted({str(r.get("platform")) for r in rs})
        info["schema"] = sorted({str(r.get("schema_version")) for r in rs})
        out.append(info)
    return out


def _ranges(xs):
    if not xs:
        return ""
    xs, parts, a, b = sorted(xs), [], None, None
    for x in xs:
        if a is None:
            a = b = x
        elif x == b + 1:
            b = x
        else:
            parts.append(f"{a}" if a == b else f"{a}-{b}")
            a = b = x
    parts.append(f"{a}" if a == b else f"{a}-{b}")
    s = ",".join(parts)
    return s if len(s) < 40 else s[:37] + "..."


def render(files, rows, bad, infos, preset, seeds):
    L = [f"# 팀원 로그 사전 점검 (기준 프리셋 {preset}, 시드 {min(seeds)}~{max(seeds)})", "",
         f"- 파일 {len(files)}개, 읽은 판 {len(rows)}개, 읽지 못한 줄 {len(bad)}개"]
    for b in bad[:10]:
        L.append(f"  - 읽지 못함: {b}")
    L += ["", "| 알고리즘 | 설정 | 재계획 | 프리셋 | 판 수 | 실패 판 | 문제 | 참고 |", "|---|---|---|---|---|---|---|---|"]
    for i in infos:
        L.append(f"| {i['alg']} | {i['params']} | {i['replan']} | {i['preset']} | {i['rows']} | {i['fail']} | "
                 f"{'; '.join(i['issues']) or '없음'} | {'; '.join(n for n in i['notes'] if n) or '-'} |")
    cm = Counter(c for i in infos for c in i["commits"])
    L += ["", "## 로그를 만든 환경", "", f"- 커밋: {dict(cm)}",
          f"- Python: {sorted({p for i in infos for p in i['python']})}",
          f"- 플랫폼: {sorted({p for i in infos for p in i['platform']})}",
          f"- 스키마 버전: {sorted({s for i in infos for s in i['schema']})}"]
    n_issue = sum(bool(i["issues"]) for i in infos)
    L += ["", f"## 판단", "", f"- 문제가 있는 설정 {n_issue}개 / 전체 {len(infos)}개. 문제가 없는 설정만 교차 확인(`a2_crosscheck`)에 바로 쓸 수 있다.",
          "- 문제가 있는 설정은 보낸 사람에게 먼저 확인한다. 로그를 고치거나 합치지 않는다."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--preset", default="L2")
    ap.add_argument("--seeds", default="0-99")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    seeds = parse_seeds(a.seeds)
    files, rows, bad = read_all(a.paths)
    if not files:
        print("jsonl 파일을 찾지 못했다", file=sys.stderr)
        return 2
    md = render(files, rows, bad, inspect(rows, a.preset, seeds), a.preset, seeds)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
