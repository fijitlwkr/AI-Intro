import random

import pytest

from agents import REGISTRY
from agents.greedy_agent import GreedyAgent
from agents.rule_agent import distances_to
from env import Action, PRESETS, generate
from env.rules import Cost, DONE, LOADED, State
from env.world import DEST_POS, RESTAURANT_POS
from runner.play import run_game
from tests.helpers import make_env


def play(env, agent):
    obs = env.reset()
    agent.reset(env, random.Random(0))
    while not env.done:
        action = agent.choose_action(obs)
        assert action in env.legal_actions(obs)
        obs = env.step(action).obs
    return env


def test_registered_and_invalid_settings():
    assert REGISTRY["greedy"] is GreedyAgent
    with pytest.raises(ValueError):
        GreedyAgent(heuristic="unknown")
    with pytest.raises(ValueError):
        GreedyAgent(objective="unknown")


@pytest.mark.parametrize("heuristic", ["max_distance", "mst"])
@pytest.mark.parametrize("objective", ["c1", "c2"])
def test_single_order_shortest_route_and_logs(heuristic, objective):
    env = make_env([("김치", "회사")], start=RESTAURANT_POS[0], preset="L0")
    agent = GreedyAgent(heuristic=heuristic, objective=objective)
    play(env, agent)
    distance = distances_to(DEST_POS[4])[RESTAURANT_POS[0]]
    assert env.success and env.total_c1 == distance
    assert env.total_c2 == distance + env.preset.load_time + env.preset.deliver_time
    assert env.nodes_expanded > 0 and env.nodes_generated > 0
    assert agent.metrics["mem_states"] > 0
    assert agent.metrics["plan_len"] == len(env.actions)
    assert agent.metrics["replans"] == 0
    assert "h_violations" not in agent.metrics  # 검증하지 않은 허용성을 0으로 보고하지 않는다.


@pytest.mark.parametrize("preset", ["L0", "L1", "L2", "L3"])
def test_finishes_all_presets_without_wrong_actions(preset):
    for seed in range(3):
        row = run_game(GreedyAgent(), generate(PRESETS[preset], seed), time_limit=10)
        assert row["score_success"], row
        assert row["score_wrong_actions"] == 0
        assert row["compute_nodes_expanded"] > 0


def test_all_three_menus_respect_loading_ban():
    env = make_env([("김치", "집"), ("피자", "학교"), ("탕수육", "회사")],
                   start=RESTAURANT_POS[0])
    play(env, GreedyAgent())
    assert env.success and env.wrong_actions == 0


def test_future_complaints_are_not_used_and_current_complaint_ages():
    env = make_env([("김치", "회사")], start=(0, 0), preset="L2", q=1.0,
                   complaints=[(0, "학교")])
    before = env.state
    outputs = env.successors(before, new_complaints=False)
    assert env.state == before and env.clock == 0
    for action, outcomes in outputs:
        nxt, cost, _ = env.rules.step(before, action, lambda tick: None)
        assert outcomes == [(1.0, nxt, cost)]
        assert nxt.slot == (1, before.slot[1], before.slot[2] - 1)
    assert env.nodes_expanded == 1
    assert env.nodes_generated == len(outputs)
    # 기본 확률 API는 그대로 신규 항의를 생성한다.
    no_complaint = State(before.pos, before.status, (0,))
    assert any(nxt.slot[0] == 1 for _, outcomes in env.successors(no_complaint)
               for _, nxt, _ in outcomes)


def test_reset_clears_previous_plan_and_goal_estimate_is_zero():
    agent = GreedyAgent()
    first = make_env([("김치", "집")], start=(0, 0))
    agent.reset(first, random.Random(0))
    agent.choose_action(first.state)
    assert agent._plan
    second = make_env([("피자", "회사")], start=RESTAURANT_POS[1])
    agent.reset(second, random.Random(1))
    assert not agent._plan and not agent.metrics
    assert agent.estimate(State(second.state.pos, (DONE,), (0,))) == 0
    assert agent.choose_action(second.state) == Action.LOAD


def test_c2_counts_duplicate_orders_and_service_time():
    env = make_env([("김치", "회사"), ("김치", "회사")], start=RESTAURANT_POS[0])
    agent = GreedyAgent(objective="c2")
    agent.reset(env, random.Random(0))
    distance = distances_to(DEST_POS[4])[RESTAURANT_POS[0]]
    assert agent.estimate(env.state) == 2 * (distance + 3)
    assert agent.estimate(State(DEST_POS[4], (LOADED,), (0,))) == 2


def test_search_uses_global_frontier_and_ignores_accumulated_cost():
    # h=1인 가지를 먼저 봐도, 그 뒤의 h=9보다 다른 가지의 h=2를 선택한다.
    # b는 비용이 높지만 g를 더하지 않는 Greedy는 b를 거치는 해를 반환한다.
    graph = {
        "start": [(Action.UP, "a", 1), (Action.DOWN, "b", 100)],
        "a": [(Action.UP, "c", 1)],
        "b": [(Action.RIGHT, "goal", 1)],
        "c": [(Action.LEFT, "goal", 1)],
    }

    class ToyEnv:
        def is_goal(self, state):
            return state == "goal"

        def successors(self, state, *, new_complaints):
            return [(action, [(1.0, nxt, Cost(cost, cost))])
                    for action, nxt, cost in graph[state]]

    agent = GreedyAgent()
    agent.reset(ToyEnv(), random.Random(0))
    values = {"start": 3, "a": 1, "b": 2, "c": 9, "goal": 0}
    agent.estimate = values.__getitem__
    assert list(agent._search("start")) == [Action.DOWN, Action.RIGHT]
