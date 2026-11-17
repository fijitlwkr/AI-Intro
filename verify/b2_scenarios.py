"""B2: 시나리오의 구조/도달 가능성/항의 간격/분포와 비용 이상치를 검사한다.

생성기와의 동일성은 A1 영역이다. 여기서는 저장된 내용 자체를 검사한다.
3 표준오차 경고는 탐색적 경고이며 다중 비교 때문에 곧바로 실패로 판정하지 않는다.
"""
import argparse
from collections import Counter, defaultdict, deque
import json
import math
import re
import statistics
from pathlib import Path

from env import PRESETS
from env.world import GRID, MOVES, RESTAURANT_POS, RESTAURANT_NAMES, DEST_POS, DEST_NAMES
from .b_common import files_from, read_rows, finish

NAME = re.compile(r"^(L[0-3])_(\d{3,})\.json$")


def reachable(start):
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in MOVES[queue.popleft()]:
            if nxt is not None and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def check_data(data, filename):
    errors = []
    if not isinstance(data, dict):
        return ["시나리오 최상위는 객체여야 함"]
    match = NAME.fullmatch(Path(filename).name)
    if not match:
        return ["등록된 L0~L3 시나리오 파일명이 아님"]
    preset_name, seed = match[1], int(match[2])
    p = PRESETS[preset_name]
    if data.get("preset") != preset_name or type(data.get("seed")) is not int or data.get("seed") != seed:
        errors.append("파일명과 preset/seed 불일치")
    if data.get("scenario_id") != f"{preset_name}-{seed:03d}":
        errors.append("scenario_id 불일치")
    expected_params = {"n": p.n, "q": p.q, "T": p.T,
                       "ensure_all_menus": p.ensure_all_menus, "horizon": p.horizon}
    if data.get("params") != expected_params:
        errors.append("프리셋 메타데이터 불일치")
    start = data.get("start")
    valid_start = isinstance(start, list) and len(start) == 2 and all(type(x) is int and 0 <= x < GRID for x in start)
    if not valid_start:
        errors.append("시작 위치 오류")
    elif not set(RESTAURANT_POS + DEST_POS) <= reachable(tuple(start)):
        errors.append("필수 장소 도달 불가")
    orders = data.get("orders")
    if not isinstance(orders, list) or len(orders) != p.n:
        errors.append("주문 수 오류")
    valid_orders = isinstance(orders, list) and all(
        isinstance(o, dict) and o.get("from") in RESTAURANT_NAMES and o.get("to") in DEST_NAMES for o in orders)
    if not valid_orders:
        errors.append("알 수 없는 식당 또는 배달지")
    elif p.ensure_all_menus and {o["from"] for o in orders} != set(RESTAURANT_NAMES):
        errors.append("메뉴 3종 포함 조건 위반")
    complaints = data.get("complaints")
    if not isinstance(complaints, list):
        return errors + ["항의 목록 오류"]
    if p.q == 0 and complaints:
        errors.append("q=0인데 항의가 있음")
    previous = None
    for event in complaints:
        if not isinstance(event, dict) or type(event.get("t")) is not int or not 0 <= event["t"] < p.horizon:
            errors.append("항의 시각 오류")
            continue
        if event.get("dest") not in DEST_NAMES:
            errors.append("항의 배달지 오류")
        if previous is not None and event["t"] <= previous + p.T:
            errors.append("항의 순서/마감 후 재발생 간격 위반")
        previous = event["t"]
    return errors


def distribution(data):
    per_preset = defaultdict(list)
    for row in data:
        per_preset[row["preset"]].append(row)
    results = []
    for name, rows in sorted(per_preset.items()):
        p = PRESETS[name]
        counters = {
            "menu": Counter(o["from"] for r in rows for o in r["orders"]),
            "destination": Counter(o["to"] for r in rows for o in r["orders"]),
            "start_row": Counter(r["start"][0] for r in rows),
            "start_col": Counter(r["start"][1] for r in rows),
            "complaint_destination": Counter(e["dest"] for r in rows for e in r["complaints"]),
        }
        choices = {"menu": RESTAURANT_NAMES, "destination": DEST_NAMES,
                   "start_row": range(GRID), "start_col": range(GRID), "complaint_destination": DEST_NAMES}
        checks = []
        for label, counts in counters.items():
            n = sum(counts.values())
            if n == 0:
                continue
            probability = 1 / len(choices[label])
            expected = n * probability
            se = math.sqrt(n * probability * (1 - probability))
            for item in choices[label]:
                z = (counts[item] - expected) / se
                checks.append({"field": label, "value": item, "observed": counts[item],
                               "expected": expected, "z_approx": z, "flag_3se": abs(z) > 3})
        if p.q > 0:
            trials = sum(p.horizon - sum(min(p.T, p.horizon - 1 - e["t"]) for e in r["complaints"])
                         for r in rows)
            events = sum(len(r["complaints"]) for r in rows)
            se = math.sqrt(trials * p.q * (1 - p.q))
            z = (events - trials * p.q) / se
            checks.append({"field": "complaint_rate", "eligible_ticks": trials, "observed": events,
                           "expected": trials * p.q, "z_approx": z, "flag_3se": abs(z) > 3})
        results.append({"preset": name, "scenarios": len(rows), "checks": checks,
                        "flags": [c for c in checks if c["flag_3se"]]})
    return results


def outliers(rows):
    groups = defaultdict(list)
    for r in rows:
        if r["algorithm"] != "astar" or not r["score_success"]:
            continue
        key = (r["preset"], r["replan"], json.dumps(r.get("params") or {}, sort_keys=True),
               r.get("git_commit"), json.dumps(r.get("preset_params") or {}, sort_keys=True))
        groups[key].append(r)
    result = []
    for key, group in groups.items():
        if len(group) < 4:
            result.append({"group": list(key), "games": len(group), "note": "4판 미만: IQR 생략"})
            continue
        costs = [r["score_cost"] for r in group]
        q1, _, q3 = statistics.quantiles(costs, n=4, method="inclusive")
        low, high = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
        result.append({"group": list(key), "games": len(group), "lower": low, "upper": high,
                       "seeds": [{"seed": r["seed"], "cost": r["score_cost"]} for r in group
                                 if r["score_cost"] < low or r["score_cost"] > high]})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="scenarios")
    ap.add_argument("--outlier-logs", nargs="*", default=[])
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    files = sorted(Path(args.dir).glob("*.json"))
    if not files:
        ap.error("시나리오 파일이 없습니다.")
    details, valid = [], []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            errors = check_data(data, path.name)
            if not errors:
                valid.append(data)
        except (KeyError, TypeError, ValueError) as exc:
            errors = [str(exc)]
        details.append({"file": str(path), "errors": errors})
    dist = distribution(valid)
    flags = sum(len(d["flags"]) for d in dist)
    bad = sum(bool(d["errors"]) for d in details)
    log_files = files_from(args.outlier_logs)
    costs = outliers(read_rows(log_files)) if log_files else []
    coverage = {name: sorted(r["seed"] for r in valid if r["preset"] == name) for name in PRESETS}
    complete = all(set(seeds) == set(range(100)) for seeds in coverage.values())
    report = {
        "status": "fail" if bad else ("conditional" if flags or not complete else "pass"),
        "scenario_files": len(files), "structural_failures": bad,
        "coverage_0_99_all_presets": complete, "distribution_3se_flags": flags,
        "distribution_note": "주변분포의 근사 3SE 탐색 검사. 메뉴 포함 조건/다중 비교/랜덤 추첨 수로 인해 확증 검정 아님",
        "map_source": "env/world.py의 고정 지도/식당/배달지 상수를 사용. 다른 지도는 미검증",
        "generator_equality": "A1에서 별도로 검사하며 이 검증과 독립 구현으로 간주하지 않음",
        "outlier_groups": costs, "coverage": coverage, "details": details, "groups": dist,
    }
    return finish(report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())

