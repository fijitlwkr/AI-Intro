import json

from agents import RandomAgent
from env import Agent, Action, generate
from runner.play import run_game
from runner import run as run_mod

FIELDS = {
    "schema_version", "run_id", "algorithm", "replan", "preset", "seed", "scenario_id",
    "score_cost", "score_avg_time", "score_success", "score_complaint_miss", "score_total_time",
    "failure", "compute_sec", "compute_nodes_expanded", "compute_nodes_generated", "actions",
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
