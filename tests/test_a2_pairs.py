"""검증 A2 도구: 판정 규칙, 재현성, 사전 기대 확인, 로그 없는 쌍 처리."""
import json
import random

from verify import a2_pairs as a2


def row(alg, seed, cost, avg=40.0, expired=0, complaints=2, success=True, replan="never", params=None, preset="L2"):
    return {"algorithm": alg, "seed": seed, "preset": preset, "replan": replan, "params": params or {},
            "score_cost": cost, "score_avg_time": avg, "score_expired": expired, "score_complaints": complaints,
            "score_success": success, "run_id": "r", "schema_version": 3, "git_commit": "c1"}


def make(alg_a, alg_b, diff_fn, n=100, **kw):
    rows = []
    for s in range(n):
        base = 50 + (s % 7)
        rows.append(row(alg_a, s, base + diff_fn(s), **kw))
        rows.append(row(alg_b, s, base))
    return rows


def pair(a, b, expect, i=1):
    return {"id": i, "a": a, "b": b, "expect": expect, "text": ""}


def test_classify_rules():
    assert a2.classify(-3, -1, 0.05) == "유의"
    assert a2.classify(-1, 2, 0.05) == "동률"
    assert a2.classify(-2, 0.03, 0.05) == "경계"          # 끝점이 0에서 0.05 이내
    assert a2.classify(0.04, 3, 0.05) == "경계"
    assert a2.classify(0, 0, 0.05, all_zero=True) == "동률(완전 일치)"
    assert a2.classify(0.01, 0.02, None) == "유의"       # 항의초과율은 경계 판정을 하지 않는다


def test_bootstrap_is_reproducible_and_brackets_mean():
    rng = random.Random(1)
    d = [rng.gauss(2.0, 1.0) for _ in range(100)]
    lo1, hi1 = a2.bootstrap_mean_diff(d, 2000, "k")
    lo2, hi2 = a2.bootstrap_mean_diff(d, 2000, "k")
    assert (lo1, hi1) == (lo2, hi2)
    assert lo1 < sum(d) / len(d) < hi1 and lo1 > 0


def test_clear_difference_is_significant_and_meets_expectation():
    rows = make("astar", "rule", lambda s: -5 + (s % 3) * 0.1)
    r = a2.analyze_pair(rows, pair("astar", "rule", {"score_cost": "A<B"}), "L2", 2000)
    m = r["metrics"]["score_cost"]
    assert m["class"] == "유의" and m["mean_diff"] < 0 and m["expect_met"] is True


def test_identical_policies_are_exact_tie():
    rows = make("rule", "logic", lambda s: 0)
    r = a2.analyze_pair(rows, pair("rule", "logic", {"score_cost": "tie"}), "L2", 2000)
    m = r["metrics"]["score_cost"]
    assert m["class"] == "동률(완전 일치)" and m["expect_met"] is True


def test_wrong_direction_fails_expectation():
    rows = make("greedy", "rule", lambda s: -4 + (s % 3) * 0.1)          # greedy가 낮게 나옴
    r = a2.analyze_pair(rows, pair("greedy", "rule", {"score_cost": "A>B"}), "L2", 2000)
    assert r["metrics"]["score_cost"]["expect_met"] is False


def test_noise_is_tie_not_significant():
    rng = random.Random(3)
    noise = [rng.gauss(0, 3) for _ in range(100)]
    rows = make("a", "b", lambda s: noise[s])
    r = a2.analyze_pair(rows, pair("a", "b", {"score_cost": "tie"}), "L2", 3000)
    assert r["metrics"]["score_cost"]["class"] in ("동률", "경계")


def test_missing_logs_reported_not_crashed():
    rows = make("astar", "rule", lambda s: -5)
    r = a2.analyze_pair(rows, pair("astar", "ucs", {}), "L2", 100)
    assert r["status"].startswith("로그 없음") and "ucs" in r["status"]


def test_replan_spec_selects_replan_rows():
    rows = [row("astar", s, 60, replan="never", expired=2, complaints=4) for s in range(100)] + \
           [row("astar", s, 62, replan="on_complaint", avg=44.0, expired=0, complaints=4) for s in range(100)]
    r = a2.analyze_pair(rows, pair("astar@on_complaint", "astar@never",
                                   {"complaint_rate": "A<B", "score_avg_time": "A>B"}, 7), "L2", 2000)
    assert r["n"] == 100
    assert r["metrics"]["complaint_rate"]["mean_diff"] == -0.5
    assert r["metrics"]["complaint_rate"]["expect_met"] is True
    assert r["metrics"]["score_avg_time"]["expect_met"] is True


def test_segments_and_holdout_missing():
    rows = make("astar", "rule", lambda s: -5, n=100)
    m = a2.analyze_pair(rows, pair("astar", "rule", {}), "L2", 500)["metrics"]["score_cost"]
    assert set(m["segments"]) == {"시드 0~49", "시드 50~99"}                # 보류 구간 로그가 없으면 만들지 않는다
    rows += make("astar", "rule", lambda s: -5, n=200)[200:]               # 시드 100~199 추가
    m = a2.analyze_pair(rows, pair("astar", "rule", {}), "L2", 500)["metrics"]["score_cost"]
    assert "보류 100~199" in m["segments"] and m["n"] == 100             # 주 판정은 시드 0~99만 쓴다


def test_saturation_detects_equal_success_rates():
    rows = [row(a, s, 50, success=True) for a in ("astar", "rule") for s in range(100)]
    assert a2.saturation(rows, [pair("astar", "rule", {})], "L2")["saturated"] is True
    rows += [row("greedy", s, 50, success=(s < 50)) for s in range(100)]
    assert a2.saturation(rows, [pair("astar", "greedy", {})], "L2")["saturated"] is False


def test_registered_pairs_file_is_the_seven_agreed_pairs():
    data = json.loads(a2.PAIRS_FILE.read_text(encoding="utf-8"))
    got = [(p["a"], p["b"]) for p in data["pairs"]]
    assert got == [("astar", "rule"), ("astar", "greedy"), ("rule", "logic"), ("greedy", "rule"),
                   ("astar", "ucs"), ("astar", "dfs"), ("astar@on_complaint", "astar@never")]
    assert all(c["text"].startswith("보류") or "보류" in c["text"] for c in data["candidates_unconfirmed"])


def test_main_runs_end_to_end_on_real_logs(tmp_path, capsys):
    from agents import REGISTRY
    from env.scenario import generate
    from runner.play import run_game
    rows = [run_game(REGISTRY[a](), generate("L2", sd), run_id=f"r-{a}-{sd}", git_commit="abc")
            for a in ("astar", "rule") for sd in range(5)]
    f = tmp_path / "x.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert a2.main([str(f), "--resamples", "300"]) == 0
    out = capsys.readouterr().out
    assert "쌍 비교" in out and "로그 없음" in out and "astar vs rule" in out and "포화 검사" in out
