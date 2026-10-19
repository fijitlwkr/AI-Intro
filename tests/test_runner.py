import json

from agents import RandomAgent
from env import Agent, Action, generate
from runner.play import run_game
from runner import run as run_mod

FIELDS = {
    "schema_version", "run_id", "algorithm", "replan", "params", "preset", "preset_params", "git_commit",
    "seed", "scenario_id",
    "score_cost", "score_avg_time", "score_success", "score_complaint_miss", "score_total_time",
    "failure", "compute_sec", "compute_nodes_expanded", "compute_nodes_generated",
    "compute_mem_states", "compute_h_violations", "compute_replans", "compute_depth",
    "compute_backtracks", "compute_rules", "compute_plan_len", "actions",
}


def test_log_line_has_agreed_fields():
    line = run_game(RandomAgent(), generate("L0", 0), run_id="t")
    assert FIELDS <= set(line)
    assert line["compute_nodes_expanded"] is None        # 탐색용 함수를 안 썼으면 null
    assert line["failure"] == "horizon" and line["score_success"] is False
    assert len(line["actions"]) <= line["score_total_time"]
    json.dumps(line, ensure_ascii=False)


def test_same_seed_same_game():
    a = run_game(RandomAgent(), generate("L2", 3))
    b = run_game(RandomAgent(), generate("L2", 3))
    assert a["actions"] == b["actions"] and a["score_cost"] == b["score_cost"]


class Greedy(Agent):
    """탐색용 함수를 3번 부르고 가능한 첫 행동을 낸다."""
    name = "greedy_test"

    def choose_action(self, obs):
        for _ in range(3):
            self.env.successors(obs)
        return self.env.legal_actions(obs)[0]


def test_node_counts_in_log():
    line = run_game(Greedy(), generate("L1", 0), time_limit=5)
    steps = len(line["actions"])
    assert line["compute_nodes_expanded"] == 3 * steps
    assert line["compute_nodes_generated"] >= line["compute_nodes_expanded"]


class Slow(Agent):
    name = "slow_test"

    def choose_action(self, obs):
        while True:
            self.env.successors(obs)


def test_time_limit_records_timeout_failure():
    line = run_game(Slow(), generate("L1", 0), time_limit=0.05)
    assert line["failure"] == "timeout" and line["score_success"] is False
    assert line["compute_sec"] >= 0.04


def test_replan_modes():
    class Probe(Agent):
        name = "probe"
        def choose_action(self, obs):
            return Action.UP
    p = Probe(replan="on_complaint")
    none, act = (0,), (1, 2, 20)
    assert p.needs_replan(type("O", (), {"slot": none})())        # 처음 계획
    assert not p.needs_replan(type("O", (), {"slot": none})())
    assert p.needs_replan(type("O", (), {"slot": act})())         # 새 항의
    assert not p.needs_replan(type("O", (), {"slot": act})())
    q = Probe(replan="every_step")
    assert q.needs_replan(type("O", (), {"slot": none})()) and q.needs_replan(type("O", (), {"slot": none})())
    n = Probe(replan="never")
    assert n.needs_replan(type("O", (), {"slot": act})()) and not n.needs_replan(type("O", (), {"slot": act})())


def test_cli_writes_jsonl(tmp_path):
    out = tmp_path / "x.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L0", "--seeds", "0-2", "--out", str(out)])
    lines = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 3 and all(FIELDS <= set(l) for l in lines)


def test_summarize_groups_and_nulls(tmp_path):
    from runner import summarize
    out = tmp_path / "x.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L0", "--seeds", "0-3", "--out", str(out)])
    (s,) = summarize.summarize(summarize.load_rows([out]))
    assert s["games"] == 4 and s["algorithm"] == "random" and s["preset"] == "L0"
    assert s["miss_pooled"] is None and s["nodes_expanded"] is None     # 해당 없음은 null
    assert 0 <= s["success_rate"] <= 1


# ---------------------------------------------------------------- 특성 지표 보고
class Reporter(Agent):
    """판마다 지표를 알리는 에이전트."""
    name = "reporter_test"

    def choose_action(self, obs):
        self.report("backtracks", 2)
        self.report("backtracks", 3)
        self.report("mem_states", 10)
        self.report("mem_states", 4)        # 더 작은 값은 최대값에 영향 없음
        self.report("rules", 7)
        self.report("rules", 5)             # 마지막 값
        return self.env.legal_actions(obs)[0]


def test_reported_metrics_are_aggregated_and_logged():
    line = run_game(Reporter(), generate("L1", 0), time_limit=5)
    steps = len(line["actions"])
    assert line["compute_backtracks"] == 5 * steps          # 합계
    assert line["compute_mem_states"] == 10                 # 최대
    assert line["compute_rules"] == 5                       # 마지막 값
    assert line["compute_depth"] is None                    # 알리지 않으면 null


def test_unknown_metric_name_is_rejected():
    import pytest
    a = Reporter()
    with pytest.raises(KeyError):
        a.report("not_a_metric", 1)


def test_metrics_are_cleared_between_games():
    a = Reporter()
    first = run_game(a, generate("L1", 0), time_limit=5)
    second = run_game(a, generate("L1", 1), time_limit=5)
    assert second["compute_backtracks"] == 5 * len(second["actions"])      # 지난 판 값이 남지 않는다


def test_replans_counted_by_needs_replan():
    from env import Agent as A

    class P(A):
        name = "p"
        def choose_action(self, obs):
            self.needs_replan(obs)
            return Action.UP

    none, act = (0,), (1, 2, 20)
    for mode, slots, expect in [
        ("never", [none, none, act, act], 0),
        ("on_complaint", [none, none, act, act, none, act], 2),          # 새 항의가 나타난 단계 2번
        ("every_step", [none, none, act, act], 3),                         # 첫 호출 제외
    ]:
        p = P(replan=mode)
        p.reset(None, None)
        for sl in slots:
            p.needs_replan(type("O", (), {"slot": sl})())
        assert p.metrics.get("replans") == expect, (mode, p.metrics)


def test_params_and_git_commit_are_recorded():
    line = run_game(RandomAgent(legal_only=True), generate("L0", 0), params={"legal_only": True}, git_commit="abc123")
    assert line["params"] == {"legal_only": True} and line["git_commit"] == "abc123"
    assert line["preset_params"]["q"] == 0.0 and line["schema_version"] == 2
    assert line["score_wrong_actions"] == 0               # 가능한 행동만 고르면 잘못된 행동이 없다


def test_parse_params():
    assert run_mod.parse_params(["a=true", "b=3", "c=0.5", "d=x"]) == {"a": True, "b": 3, "c": 0.5, "d": "x"}
