"""검증기가 잘못된 입력을 실제로 거부하는지 검사한다."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agents import RuleAgent, RandomAgent
from env import Agent, ComputeTimeout, generate
from runner.play import run_game
from runner import summarize as sm
from verify.b1_metrics import verify_row, check_aggregates
from verify.b2_scenarios import check_data, distribution
from verify.b3_algorithms import compare_case
from verify import b1_timing


@pytest.fixture
def row():
    return run_game(RuleAgent(), generate("L2", 0), git_commit="fixture")


def test_replay_accepts_original_log_and_formula(row):
    assert verify_row(row)["errors"] == []


@pytest.mark.parametrize("field", ["score_cost", "score_avg_time", "score_total_time",
                                   "score_wrong_actions", "score_complaints", "score_expired"])
def test_replay_rejects_tampered_metric(row, field):
    changed = deepcopy(row)
    changed[field] += 1
    assert any(field in error for error in verify_row(changed)["errors"])


def test_replay_rejects_tampered_hash_and_post_goal_action(row):
    changed = deepcopy(row)
    changed["scenario_sha256"] = "0" * 64
    assert any("sha256" in error for error in verify_row(changed)["errors"])
    changed = deepcopy(row)
    changed["actions"].append(0)
    assert any("종료 뒤 행동" in error for error in verify_row(changed)["errors"])


def test_no_complaint_is_null_not_zero():
    row = run_game(RandomAgent(), generate("L0", 0))
    assert not verify_row(row)["errors"]
    row["score_complaint_miss"] = 0
    assert any("score_complaint_miss" in error for error in verify_row(row)["errors"])


def test_timeout_prefix_is_a_valid_incomplete_record():
    class Prefix(Agent):
        def choose_action(self, obs):
            if self.env.actions:
                raise ComputeTimeout()
            return self.env.legal_actions(obs)[0]
    row = run_game(Prefix(), generate("L2", 0))
    assert row["failure"] == "timeout"
    assert not verify_row(row)["errors"]


def test_old_schema_warns_instead_of_claiming_input_identity(row):
    row.pop("scenario_sha256")
    result = verify_row(row)
    assert not result["errors"]
    assert any("해시 없음" in w for w in result["warnings"])


def test_aggregate_check_detects_wrong_pooled_ratio(row, monkeypatch):
    rows = [row]
    assert not check_aggregates(rows)[0]["errors"]
    original = sm.summarize

    def corrupt(values):
        result = original(values)
        result[0]["miss_pooled"] = -1
        return result

    monkeypatch.setattr(sm, "summarize", corrupt)
    assert "miss_pooled" in check_aggregates(rows)[0]["errors"]


@pytest.fixture
def scenario():
    return generate("L2", 17).to_json()


def test_scenario_content_accepts_valid_file(scenario):
    assert not check_data(scenario, "L2_017.json")


@pytest.mark.parametrize("change", ["start", "order_count", "menu", "complaint_spacing", "seed", "params"])
def test_scenario_content_rejects_structural_corruption(scenario, change):
    if change == "start":
        scenario["start"] = [-1, 0]
    elif change == "order_count":
        scenario["orders"].pop()
    elif change == "menu":
        scenario["orders"][0]["from"] = "없는 메뉴"
    elif change == "complaint_spacing":
        scenario["complaints"] = [{"t": 5, "dest": "집"}, {"t": 6, "dest": "학교"}]
    elif change == "seed":
        scenario["seed"] = 18
    else:
        scenario["params"]["T"] += 1
    assert check_data(scenario, "L2_017.json")


def test_scenario_duplicates_are_legal_and_differ_from_generator_check(scenario):
    scenario["orders"] = ([{"from": "김치", "to": "집"}] * 6 +
                          [{"from": "피자", "to": "학교"}, {"from": "탕수육", "to": "회사"}])
    assert not check_data(scenario, "L2_017.json")


def test_distribution_flags_extreme_bias_without_declaring_a_bug(scenario):
    rows = [deepcopy(scenario) for _ in range(100)]
    for row in rows:
        row["start"] = [0, 0]
    report = distribution(rows)
    assert any(flag["field"] == "start_row" for flag in report[0]["flags"])


def test_algorithm_crosscheck_detects_wrong_optimum():
    reference = {"algorithm": "ucs", "score_success": True, "score_cost": 10,
                 "score_avg_time": 5, "score_wrong_actions": 0, "params": {}, "actions": []}
    candidate = {**reference, "algorithm": "astar", "score_cost": 11}
    assert compare_case([reference, candidate], "c1")["errors"]
    assert not compare_case([reference, candidate], "c2")["errors"]


@pytest.mark.parametrize("logged,passed", [(.2001, True), (.203, False)])
def test_external_timer_tolerance_detects_mismatch(monkeypatch, logged, passed):
    class Dummy:
        def choose_action(self, obs):
            return 0
    monkeypatch.setitem(b1_timing.REGISTRY, "dummy", Dummy)
    times = iter([0, 200_000_000])
    monkeypatch.setattr(b1_timing.time, "perf_counter_ns", lambda: next(times))

    def run(agent, scenario):
        agent.choose_action(None)
        return {"compute_sec": logged, "score_success": True}

    monkeypatch.setattr(b1_timing, "run_game", run)
    result = b1_timing.measured_game("dummy", {}, SimpleNamespace(seed=0))
    assert result["within_tolerance"] is passed

