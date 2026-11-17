"""검증 A2: 사전 확정한 비교쌍의 해석 변별력 검사.

python -m verify.a2_pairs logs/*.jsonl [--preset L2] [--resamples 10000] [--json out.json]

하는 일
 1. 포화 검사: 비교에 나온 알고리즘 전원의 성공률이 같으면 그 지표는 포화다.
 2. 쌍 비교: 같은 시드끼리 짝지은 차이(A-B)에 부트스트랩 95% 신뢰구간(백분위법)을 구하고 판정한다.
      경계    끝점이 0에서 band 이내 (band: 총비용·평균배달시간 0.05. 항의초과율은 경계 판정을 하지 않는다)
      유의    구간이 0을 제외
      동률    구간이 0을 포함
      동률(완전 일치)  모든 시드에서 차이가 정확히 0 (구간이 [0, 0]이라 경계 규칙에 걸리지 않게 따로 둔다)
 3. 사전 기대(verify/a2_registered_pairs.json)와 일치하는지 본다. 방향만 보고 크기는 보지 않는다.
 4. 순위 안정성: 시드 0~49, 50~99, 보류 100~199에서 차이의 부호가 같은지.
 5. 시드 수 충분성: 최소 검출 차이 1.96*sd/sqrt(n). 지금 n과 n*2일 때.
재표집은 (쌍, 지표)마다 고정된 난수 시드를 써서 같은 로그에서 같은 구간이 나온다.
"""
import argparse
import json
import math
import random
import statistics
import sys
import zlib
from pathlib import Path

from runner import summarize as sm

PAIRS_FILE = Path(__file__).with_name("a2_registered_pairs.json")
BASE_SEED = 20261117
BAND = {"score_cost": 0.05, "score_avg_time": 0.05, "complaint_rate": None}
METRIC_LABEL = {"score_cost": "총비용", "score_avg_time": "평균배달시간", "complaint_rate": "항의초과율"}
SEGMENTS = [("시드 0~49", 0, 49), ("시드 50~99", 50, 99), ("보류 100~199", 100, 199)]


# ------------------------------------------------------------ 로그 고르기
def parse_spec(text):
    """'astar', 'astar@on_complaint', 'idastar:memo=true@never' -> (알고리즘, 설정, 재계획)."""
    body, _, replan = text.partition("@")
    name, params = sm.parse_spec(body)
    return name, params, replan or "never"


def pick(rows, spec, preset):
    name, params, replan = parse_spec(spec)
    return {r["seed"]: r for r in rows
            if r["algorithm"] == name and r["preset"] == preset and r["replan"] == replan
            and all((r.get("params") or {}).get(k) == v for k, v in params.items())}


# ------------------------------------------------------------ 통계
def _rng(key):
    return random.Random(BASE_SEED + zlib.crc32(key.encode()))


def bootstrap_mean_diff(diffs, resamples, key):
    rng, n = _rng(key), len(diffs)
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(resamples))
    return means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1]


def bootstrap_rate_diff(pairs, resamples, key):
    """pairs = [(초과A, 항의A, 초과B, 항의B), ...]. 시드를 재표집해 합산 비율의 차이(A-B)를 구한다."""
    rng, n = _rng(key), len(pairs)
    out = []
    for _ in range(resamples):
        ea = ca = eb = cb = 0
        for p in rng.choices(pairs, k=n):
            ea += p[0]; ca += p[1]; eb += p[2]; cb += p[3]
        if ca and cb:
            out.append(ea / ca - eb / cb)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def classify(lo, hi, band, all_zero=False):
    if all_zero:
        return "동률(완전 일치)"
    if band is not None and (abs(lo) <= band or abs(hi) <= band):
        return "경계"
    return "유의" if (lo > 0 or hi < 0) else "동률"


def meets(expect, cls, mean):
    """사전 기대와 판정이 맞는지. expect: 'A<B', 'A>B', 'tie'."""
    if expect == "tie":
        return cls.startswith("동률")
    if cls == "유의":
        return (mean < 0) == (expect == "A<B")
    return False


# ------------------------------------------------------------ 한 쌍 분석
def metric_series(ra, rb, seeds, metric):
    if metric == "complaint_rate":
        return [(ra[s]["score_expired"], ra[s]["score_complaints"], rb[s]["score_expired"], rb[s]["score_complaints"])
                for s in seeds]
    return [ra[s][metric] - rb[s][metric] for s in seeds]


def point_diff(series, metric):
    if metric == "complaint_rate":
        ea = sum(p[0] for p in series); ca = sum(p[1] for p in series)
        eb = sum(p[2] for p in series); cb = sum(p[3] for p in series)
        return (ea / ca - eb / cb) if ca and cb else None
    return sum(series) / len(series)


def analyze_pair(rows, pair, preset, resamples):
    ra, rb = pick(rows, pair["a"], preset), pick(rows, pair["b"], preset)
    seeds = sorted(set(ra) & set(rb))
    res = {"id": pair["id"], "a": pair["a"], "b": pair["b"], "text": pair["text"], "n": len(seeds), "metrics": {}}
    if not seeds:
        missing = [s for s, r in ((pair["a"], ra), (pair["b"], rb)) if not r]
        res["status"] = "로그 없음: " + (", ".join(missing) if missing else "같은 시드가 없음")
        return res
    res["status"] = "분석"
    in_range = [s for s in seeds if s <= 99]
    for metric in ("score_cost", "score_avg_time", "complaint_rate"):
        main_seeds = in_range or seeds
        series = metric_series(ra, rb, main_seeds, metric)
        mean = point_diff(series, metric)
        if mean is None:
            res["metrics"][metric] = {"status": "계산 불가(항의 0건)"}
            continue
        key = f"{pair['id']}|{metric}|{preset}"
        if metric == "complaint_rate":
            lo, hi = bootstrap_rate_diff(series, resamples, key)
            all_zero = all(p[0] == p[2] and p[1] == p[3] for p in series)
            sd = None
        else:
            lo, hi = bootstrap_mean_diff(series, resamples, key)
            all_zero = all(d == 0 for d in series)
            sd = statistics.stdev(series) if len(series) > 1 else None
        cls = classify(lo, hi, BAND[metric], all_zero)
        m = {"n": len(main_seeds), "mean_diff": mean, "ci": [lo, hi], "class": cls}
        if sd is not None:
            m["mdd_now"] = 1.96 * sd / math.sqrt(len(series))
            m["mdd_double"] = 1.96 * sd / math.sqrt(2 * len(series))
        exp = pair["expect"].get(metric)
        if exp:
            m["expect"] = exp
            m["expect_met"] = meets(exp, cls, mean)
        segs = {}
        for label, a, b in SEGMENTS:
            ss = [s for s in seeds if a <= s <= b]
            if ss:
                segs[label] = {"n": len(ss), "mean_diff": point_diff(metric_series(ra, rb, ss, metric), metric)}
        m["segments"] = segs
        res["metrics"][metric] = m
    return res


# ------------------------------------------------------------ 포화
def saturation(rows, pairs, preset):
    specs = sorted({p[k] for p in pairs for k in ("a", "b")})
    rates = {}
    for spec in specs:
        picked = [r for r in pick(rows, spec, preset).values() if r["seed"] <= 99]
        if picked:
            rates[spec] = sum(1 for r in picked if r["score_success"]) / len(picked)
    return {"rates": rates, "saturated": len(rates) > 1 and len(set(rates.values())) == 1}


# ------------------------------------------------------------ 보고
def fmt(x, nd=3):
    return "-" if x is None else f"{x:.{nd}f}"


def sign_text(x):
    return "0" if x == 0 else ("+" if x > 0 else "-")


def render(results, sat, notes, preset, resamples, n_rows):
    out = [f"# A2 쌍 비교 결과 ({preset}, 로그 {n_rows}판, 재표집 {resamples}회)", ""]
    out += [f"- 주의: {n}" for n in notes] or ["- `summarize` 경고 없음"]
    out += ["", "## 포화 검사 (성공률)", ""]
    if sat["rates"]:
        out.append(" | ".join(f"{k} {v:.0%}" for k, v in sat["rates"].items()))
        out.append("")
        out.append("**포화: 비교 대상 전원의 성공률이 같다. 성공률은 비교 근거로 쓰지 않는다.**" if sat["saturated"]
                   else "포화 아님: 알고리즘마다 성공률이 다르다.")
    else:
        out.append("로그가 없어 판정하지 않음.")
    out += ["", "## 쌍 비교 (차이 = A - B, 시드 0~99, 같은 시드끼리 짝지음)", "",
            "| # | 쌍 (A vs B) | 지표 | n | 평균차 | 95% 구간 | 판정 | 사전 기대 | 기대 충족 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "분석":
            out.append(f"| {r['id']} | {r['a']} vs {r['b']} | - | - | - | - | {r['status']} | {r['text']} | - |")
            continue
        for metric, m in r["metrics"].items():
            if "class" not in m:
                out.append(f"| {r['id']} | {r['a']} vs {r['b']} | {METRIC_LABEL[metric]} | - | - | - | {m['status']} | - | - |")
                continue
            exp = m.get("expect")
            met = "-" if exp is None else ("예" if m["expect_met"] else "**아니오**")
            out.append(f"| {r['id']} | {r['a']} vs {r['b']} | {METRIC_LABEL[metric]} | {m['n']} | {fmt(m['mean_diff'])} | "
                       f"[{fmt(m['ci'][0])}, {fmt(m['ci'][1])}] | {m['class']} | {exp or '없음'} | {met} |")
    out += ["", "## 순위 안정성: 구간별 평균차의 부호 (판정이 `유의`인 지표만 일치 여부를 본다)", "", "| # | 지표 | " + " | ".join(s[0] for s in SEGMENTS) + " | 부호 일치 |", "|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "분석":
            continue
        for metric, m in r["metrics"].items():
            if "segments" not in m:
                continue
            cells, signs = [], []
            for label, _, _ in SEGMENTS:
                s = m["segments"].get(label)
                cells.append("로그 없음" if s is None else f"{sign_text(s['mean_diff'])} ({fmt(s['mean_diff'], 2)}, n={s['n']})")
                if s is not None and s["mean_diff"] is not None:
                    signs.append(sign_text(s["mean_diff"]))
            if m["class"] != "유의":
                verdict = "해당 없음(" + m["class"] + ")"          # 차이가 0과 구별되지 않으면 부호가 흔들리는 것이 정상이다
            else:
                verdict = "예" if len(set(signs)) <= 1 else "**아니오**"
            out.append(f"| {r['id']} | {METRIC_LABEL[metric]} | " + " | ".join(cells) + f" | {verdict} |")
    out += ["", "## 시드 수 충분성 (총비용·평균배달시간, 최소 검출 차이 1.96*sd/sqrt(n))", "",
            "| # | 지표 | 평균차 | 최소 검출 차이(n=지금) | 최소 검출 차이(n 두 배) | 평균차가 지금 n으로 검출 가능한가 |", "|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "분석":
            continue
        for metric in ("score_cost", "score_avg_time"):
            m = r["metrics"].get(metric)
            if m and "mdd_now" in m:
                ok = "예" if abs(m["mean_diff"]) >= m["mdd_now"] else "아니오(차이가 노이즈 수준이거나 0)"
                out.append(f"| {r['id']} | {METRIC_LABEL[metric]} | {fmt(m['mean_diff'])} | {fmt(m['mdd_now'])} | {fmt(m['mdd_double'])} | {ok} |")
    out += ["", "## 읽는 법", "",
            "- 사전 기대는 방향만 본다. 판정이 `경계`이면 시드 200개로 다시 확인한다. `동률`은 '차이를 검출하지 못했다'이지 '같다'가 아니다.",
            "- 같은 코드로 다시 돌린 재현은 구현 오류를 잡지 못한다. 이 표는 변별력(노이즈와 구별되는지)만 본다."]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--preset", default="L2")
    ap.add_argument("--resamples", type=int, default=10000)
    ap.add_argument("--pairs", default=str(PAIRS_FILE))
    ap.add_argument("--json")
    args = ap.parse_args(argv)

    paths = [p for g in args.logs for p in (sorted(Path().glob(g)) if any(c in g for c in "*?[") else [Path(g)])]
    rows, _ = sm.dedupe(sm.load_rows(paths))
    pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))["pairs"]
    summary = sm.summarize([r for r in rows if r["preset"] == args.preset])
    notes = sm.warnings_for(rows, summary, len(sm.n_versions_set(rows)))
    results = [analyze_pair(rows, p, args.preset, args.resamples) for p in pairs]
    sat = saturation(rows, pairs, args.preset)
    print(render(results, sat, notes, args.preset, args.resamples, len(rows)))
    if args.json:
        Path(args.json).write_text(json.dumps({"results": results, "saturation": sat, "notes": notes}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
