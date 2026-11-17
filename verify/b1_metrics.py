"""B1: 기존 환경으로 행동열 재생 + 별도 산식으로 점수/집계 재계산.

이 검증은 독립 시뮬레이터가 아니다. DeliveryEnv의 전이/사건 판정을 공유한다.
python -m verify.b1_metrics logs --out logs/runs/b/b1_metrics.json
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math

from env import DeliveryEnv, PRESETS
from env.presets import Preset
from env.scenario import scenario_path, load, generate
from runner import summarize as sm
from .b_common import files_from, read_rows, finish


def equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if a is None or b is None:
        return a is b
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=0, abs_tol=1e-9)


def verify_row(row, scenario=None):
    errors, warnings = [], []
    preset = Preset(**row["preset_params"]) if row.get("preset_params") else PRESETS[row["preset"]]
    if not row.get("preset_params"):
        warnings.append("preset_params 없음: 현재 프리셋 사용")
    if scenario is None:
        path = scenario_path(row["preset"], row["seed"])
        if path.exists():
            scenario = load(path)
        else:
            scenario = generate(preset, row["seed"])
            warnings.append("시나리오 파일 없음: 기록 프리셋으로 생성")
    if scenario.scenario_id != row["scenario_id"] or scenario.seed != row["seed"] or scenario.preset != row["preset"]:
        errors.append("시나리오 식별 정보 불일치")
    digest = hashlib.sha256(json.dumps(scenario.to_json(), sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode()).hexdigest()
    if row.get("scenario_sha256") and row["scenario_sha256"] != digest:
        errors.append("scenario_sha256 불일치")
    if not row.get("scenario_sha256"):
        warnings.append("시나리오 해시 없음: 과거 입력 내용 동일성 미확인")
    env = DeliveryEnv(scenario, preset)
    amounts = [c for _, _, c in scenario.combos()]
    clock = move = wrong = expired = completion = 0
    arrived = int(any(t == 0 for t, _ in scenario.complaints))
    integral = 0
    for index, action in enumerate(row["actions"]):
        if type(action) is not int or not 0 <= action <= 5:
            errors.append(f"actions[{index}]: 행동 번호 오류")
            break
        if env.done:
            errors.append(f"actions[{index}]: 종료 뒤 행동")
            break
        before = env.state.status
        result = env.step(action)
        clock += result.info.dt
        integral += sum(c for c, status in zip(amounts, before) if status != 2) * result.info.dt
        move += result.info.kind in ("move", "bump")
        wrong += result.info.kind == "wrong"
        expired += result.info.expired
        arrived += result.info.arrived
        completion += sum(c for c, old, new in zip(amounts, before, result.obs.status)
                          if old != 2 and new == 2) * clock
    unfinished = sum(c for c, status in zip(amounts, env.state.status) if status != 2)
    if integral != completion + unfinished * clock:
        errors.append("c2 시간 적분 항등식 불일치")
    failure = row.get("failure")
    if failure not in (None, "horizon", "timeout"):
        errors.append("알 수 없는 failure")
    if failure is None and not env.success:
        errors.append("미완료 행동열인데 failure가 없음")
    if failure == "horizon" and (not env.done or env.success):
        errors.append("horizon 종료 조건 불일치")
    if failure == "timeout" and env.done:
        errors.append("이미 종료된 행동열에 timeout 표시")
    expected = {
        "score_cost": move + preset.wrong_penalty * wrong + preset.P * expired,
        "score_avg_time": (completion + unfinished * preset.horizon) / sum(amounts),
        "score_success": env.success and clock <= preset.horizon and failure != "timeout",
        "score_complaint_miss": expired / arrived if arrived else None,
        "score_total_time": clock, "score_wrong_actions": wrong,
        "score_complaints": arrived, "score_expired": expired,
    }
    for field, value in expected.items():
        if field not in row or not equal(row[field], value):
            errors.append(f"{field}: 기록={row.get(field)!r}, 재계산={value!r}")
    if row.get("compute_sec") is None or not math.isfinite(row["compute_sec"]) or row["compute_sec"] < 0:
        errors.append("compute_sec는 유한한 비음수여야 함")
    return {"source": row.get("_src"), "errors": errors, "warnings": warnings, "expected": expected}


def check_aggregates(rows):
    groups = defaultdict(list)
    for row in rows:
        key = (row["algorithm"], row["preset"], row["replan"],
               json.dumps(row.get("params") or {}, sort_keys=True),
               json.dumps(row.get("preset_params") or {}, sort_keys=True))
        groups[key].append(row)
    results = []
    for key, group in groups.items():
        try:
            summaries = sm.summarize(group)
            if len(summaries) != 1:
                raise ValueError("집계 그룹이 예상과 다름")
            summary = summaries[0]
            n = len(group)
            costs = sorted((r["score_cost"] for r in group), reverse=True)
            arrived = sum(r["score_complaints"] for r in group)
            actions = sum(len(r["actions"]) for r in group)
            expected = {
                "cost_mean": sum(costs) / n,
                "avg_time_mean": sum(r["score_avg_time"] for r in group) / n,
                "success_rate": sum(bool(r["score_success"]) for r in group) / n,
                "miss_pooled": sum(r["score_expired"] for r in group) / arrived if arrived else None,
                "wrong_rate": sum(r["score_wrong_actions"] for r in group) / actions if actions else None,
                "worst10": sum(costs[:math.ceil(n * .1)]) / math.ceil(n * .1),
            }
            errors = [field for field, value in expected.items() if not equal(summary[field], value)]
            results.append({"group": list(key), "games": n, "errors": errors})
        except (KeyError, TypeError, ValueError) as exc:
            results.append({"group": list(key), "errors": [str(exc)]})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    files = files_from(args.inputs)
    if not files:
        ap.error("검증할 JSONL이 없습니다.")
    rows = read_rows(files)
    if not rows:
        ap.error("JSONL에 판 기록이 없습니다.")
    details = []
    for row in rows:
        try:
            details.append(verify_row(row))
        except (KeyError, TypeError, ValueError, RuntimeError, ZeroDivisionError) as exc:
            details.append({"source": row.get("_src"), "errors": [str(exc)], "warnings": []})
    groups = check_aggregates(rows)
    bad = sum(bool(r["errors"]) for r in details)
    report = {
        "status": "fail" if bad or any(g["errors"] for g in groups) else "conditional",
        "games": len(rows), "mismatching_games": bad, "aggregate_groups": len(groups),
        "aggregate_mismatches": sum(bool(g["errors"]) for g in groups),
        "provenance_warning_games": sum(bool(r["warnings"]) for r in details),
        "independence": "동일 DeliveryEnv 재생 + 별도 산식. 명세 기반 독립 시뮬레이터 아님",
        "limitation": "행동열로 계산시간, 탐색 노드수, 미공개 과거 입력 내용을 복원할 수 없음",
        "details": details, "groups": groups,
    }
    return finish(report, args.out)


if __name__ == "__main__":
    raise SystemExit(main())

