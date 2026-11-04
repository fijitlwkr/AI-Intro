from copy import deepcopy
import json
import random

import pytest

from agents.astar_agent import AStarAgent
from env import ComputeTimeout
from runner.play import run_game
from runner.replanning import comparison, main
from tests.helpers import make_env
from tests.test_astar_agent import play


@pytest.mark.parametrize("mode", ["never", "every_step"])
def test_number_of_searches_and_reset(mode):
    env = make_env([("김치", "회사")], start=(1, 2))
    agent = AStarAgent(replan=mode)
    original = agent._search
    observed = []

    def search(state):
        observed.append(state)
        return original(state)

    agent._search = search
    play(env, agent)
    expected = 1 if mode == "never" else len(env.actions)
    assert len(observed) == expected
    assert agent.metrics["replans"] == expected - 1
    assert observed[0].pos == (1, 2)
    agent.reset(env, random.Random(0))
    assert not agent._plan and not agent.metrics


def test_new_complaint_changes_the_plan_and_avoids_penalty():
    results = {}
    for mode in ("never", "every_step"):
        # 첫 이동 후 출발점에 항의가 발생한다. 돌아가는 두 걸음으로 벌금 40을 피한다.
        env = make_env([("피자", "공원")], start=(0, 7), complaints=[(1, "집")],
                       preset="L2", q=0, T=10, P=40)
        agent = AStarAgent(replan=mode)
        play(env, agent)
        results[mode] = (env.total_c1, env.expired)
    assert results["never"] == (61, 1)
    assert results["every_step"] == (23, 0)


@pytest.mark.parametrize("objective", ["c1", "c2"])
def test_no_complaints_preserves_optimal_objective(objective):
    scores = []
    for mode in ("never", "every_step"):
        env = make_env([("김치", "회사"), ("피자", "학교")], start=(0, 0))
        scores.append(play(env, AStarAgent(replan=mode, objective=objective)))
    index = 0 if objective == "c1" else 1
    assert scores[0][index] == scores[1][index]


def test_timeout_during_replanning_is_reported_as_failure():
    env = make_env([("김치", "회사")], start=(1, 2), preset="L0")

    class InterruptedAgent(AStarAgent):
        def _search(self, state):
            if self.metrics["replans"]:
                raise ComputeTimeout()
            return super()._search(state)

    row = run_game(InterruptedAgent(replan="every_step"), env.scenario)
    assert row["failure"] == "timeout" and row["score_success"] is False
    assert len(row["actions"]) == 1 and row["compute_replans"] == 1


def test_experiment_runner_writes_paired_outputs(tmp_path):
    result = main(["--preset", "L2", "--seeds", "0", "--time-limit", "10",
                   "--out-dir", str(tmp_path)])
    assert result["paired"]["paired_games"] == 1
    assert result["paired"]["both_successful"] == 1
    assert len(result["summary"]) == 2
    rows = []
    for path in tmp_path.glob("*.jsonl"):
        rows.extend(json.loads(s) for s in path.read_text(encoding="utf-8").splitlines())
    assert {r["replan"] for r in rows} == {"never", "every_step"}
    assert all(r["params"] == {"heuristic": "mst", "objective": "c1"} for r in rows)
    assert (tmp_path / "L2_mst_c1_notion.csv").exists()
    bad = deepcopy(rows)
    bad[0]["git_commit"] = "different"
    with pytest.raises(ValueError, match="코드 버전"):
        comparison(bad, [0])
    with pytest.raises(ValueError, match="모든 시드"):
        comparison(rows, [0, 1])
