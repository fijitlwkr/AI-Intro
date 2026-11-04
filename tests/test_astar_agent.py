from collections import deque
from heapq import heappop, heappush
from itertools import count
from math import inf
import random

import pytest

from agents import REGISTRY
from agents.astar_agent import AStarAgent
from agents.greedy_agent import GreedyAgent
from agents.heuristics import DeliveryHeuristic
from env import Action, ComputeTimeout
from env.rules import Cost, State
from tests.helpers import make_env

NAMES = ("max_distance", "mst", "constraint")


def exact_remaining_costs(env, objective):
    """독립적인 작은 문제 오라클: 도달 가능한 그래프를 만든 뒤 역방향 Dijkstra."""
    queue, seen, reverse, goals = deque([env.state]), {env.state}, {}, []
    while queue:
        state = queue.popleft()
        if env.rules.is_goal(state):
            goals.append(state)
            continue
        for action in env.rules.legal_actions(state):
            nxt, cost, _ = env.rules.step(state, action, lambda tick: None)
            reverse.setdefault(nxt, []).append((state, getattr(cost, objective)))
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    values = {goal: 0 for goal in goals}
    serial = count()
    heap = [(0, next(serial), goal) for goal in goals]
    while heap:
        cost, _, state = heappop(heap)
        if cost != values[state]:
            continue
        for previous, edge in reverse.get(state, ()):
            candidate = cost + edge
            if candidate < values.get(previous, inf):
                values[previous] = candidate
                heappush(heap, (candidate, next(serial), previous))
    return values


def play(env, agent):
    obs = env.reset()
    agent.reset(env, random.Random(0))
    while not env.done:
        action = agent.choose_action(obs)
        assert action in env.legal_actions(obs)
        obs = env.step(action).obs
    assert env.success
    return env.total_c1, env.total_c2


def test_registered_and_invalid_settings():
    assert REGISTRY["astar"] is AStarAgent
    with pytest.raises(ValueError):
        AStarAgent(heuristic="bad")
    with pytest.raises(ValueError):
        AStarAgent(objective="bad")


@pytest.mark.parametrize("objective", ["c1", "c2"])
@pytest.mark.parametrize("orders", [
    [("김치", "회사"), ("김치", "회사")],
    [("김치", "회사"), ("피자", "학교"), ("탕수육", "집")],
    [("김치", "회사"), ("김치", "집"), ("피자", "학교"), ("탕수육", "집")],
])
def test_admissible_on_every_reachable_small_state_and_optimal_plan(orders, objective):
    env = make_env(orders, start=(0, 0), preset="L1")
    exact = exact_remaining_costs(env, objective)
    expected = exact[env.state]
    for name in NAMES:
        heuristic = DeliveryHeuristic(env, name, objective)
        for state, remaining in exact.items():
            estimate = heuristic(state)
            assert 0 <= estimate <= remaining, (name, objective, state, estimate, remaining)
            if name == "constraint":
                assert estimate >= DeliveryHeuristic(env, "mst", objective)(state)
        agent = AStarAgent(heuristic=name, objective=objective)
        costs = play(env, agent)
        assert costs[0 if objective == "c1" else 1] == expected
        assert env.wrong_actions == 0
        assert agent.metrics["replans"] == 0
        assert env.nodes_expanded > 0


@pytest.mark.parametrize("objective", ["c1", "c2"])
@pytest.mark.parametrize("name", ["max_distance", "mst"])
def test_same_heuristics_as_greedy(name, objective):
    env = make_env([("김치", "회사"), ("피자", "학교")], start=(2, 4))
    greedy = GreedyAgent(heuristic=name, objective=objective)
    greedy.reset(env, random.Random(0))
    heuristic = DeliveryHeuristic(env, name, objective)
    for status in ((0, 0), (1, 0), (2, 1), (2, 2)):
        for pos in ((0, 0), (1, 2), (6, 4)):
            state = State(pos, status, (0,))
            assert heuristic(state) == greedy.estimate(state)


def test_constraint_pattern_really_enforces_menu_ban():
    orders = [("김치", "공원"), ("피자", "공원"), ("탕수육", "공원")]
    banned = make_env(orders, start=(1, 2), menu_ban=True)
    free = make_env(orders, start=(1, 2), menu_ban=False)
    h_ban = DeliveryHeuristic(banned, "constraint")
    h_free = DeliveryHeuristic(free, "constraint")
    h_ban(banned.state)
    h_free(free.state)
    # 적재 패턴의 최적 비용을 비교한다. 먼 공원으로 먼저 다녀와야 해서 더 비싸다.
    assert h_ban.pattern.estimate(banned.state) > h_free.pattern.estimate(free.state)


def test_reopens_state_when_cheaper_path_arrives_with_inconsistent_heuristic():
    graph = {
        "start": [(Action.UP, "a", 3), (Action.DOWN, "b", 1)],
        "a": [(Action.RIGHT, "goal", 3)],
        "b": [(Action.LEFT, "a", 1)],
    }
    expanded = []

    class ToyEnv:
        def _check_deadline(self):
            pass

        def is_goal(self, state):
            return state == "goal"

        def successors(self, state, *, new_complaints):
            expanded.append(state)
            return [(action, [(1.0, nxt, Cost(cost, cost))])
                    for action, nxt, cost in graph[state]]

    class Estimate:
        cache = {}
        records = 0

        def __call__(self, state):
            return {"start": 0, "a": 0, "b": 4, "goal": 0}[state]

    agent = AStarAgent()
    agent.reset(ToyEnv(), random.Random(0))
    agent.estimator = Estimate()
    assert list(agent._search("start")) == [Action.DOWN, Action.LEFT, Action.RIGHT]
    assert expanded.count("a") == 2


def test_reset_and_timeout_during_heuristic_preprocessing():
    env = make_env([("김치", "회사")], start=(0, 0))
    agent = AStarAgent(heuristic="constraint")
    agent.reset(env, random.Random(0))
    agent.choose_action(env.state)
    assert agent._plan and agent.estimator.pattern is not None
    agent.reset(env, random.Random(0))
    assert not agent._plan and not agent.estimator.cache and agent.estimator.pattern is None
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.state)


def test_active_complaint_does_not_break_admissibility_or_model_optimality():
    env = make_env([("김치", "회사")], start=(0, 0), preset="L2", q=0,
                   complaints=[(0, "집")], T=5)
    exact = exact_remaining_costs(env, "c1")
    expected = exact[env.state]
    for name in NAMES:
        env.reset()
        h = DeliveryHeuristic(env, name)
        for state, remaining in exact.items():
            assert h(state) <= remaining
        assert play(env, AStarAgent(heuristic=name))[0] == expected
