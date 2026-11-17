import random

import pytest

from agents import REGISTRY
from agents.astar_agent import AStarAgent
from agents.search_agents import UCSAgent, BFSAgent, DFSAgent, IDSAgent, IDAStarAgent
from env import ComputeTimeout
from tests.helpers import make_env
from tests.test_astar_agent import exact_remaining_costs

ORDERS = [("김치", "회사"), ("피자", "학교"), ("탕수육", "집")]
START = (5, 5)


def play(env, agent):
    obs = env.reset()
    agent.reset(env, random.Random(0))
    while not env.done:
        action = agent.choose_action(obs)
        assert action in env.legal_actions(obs)
        obs = env.step(action).obs
    assert env.success
    return env.total_c1, env.total_c2


def fewest_actions(env):
    """독립 오라클: 규칙만 써서 목표까지의 최소 행동 수를 센다."""
    from collections import deque
    queue, depth = deque([env.state]), {env.state: 0}
    while queue:
        state = queue.popleft()
        if env.rules.is_goal(state):
            return depth[state]
        for action in env.rules.legal_actions(state):
            nxt, _, _ = env.rules.step(state, action, lambda tick: None)
            if nxt not in depth:
                depth[nxt] = depth[state] + 1
                queue.append(nxt)


def test_registered_and_invalid_settings():
    assert REGISTRY["ucs"] is UCSAgent
    assert REGISTRY["bfs"] is BFSAgent
    assert REGISTRY["dfs"] is DFSAgent
    assert REGISTRY["ids"] is IDSAgent
    assert REGISTRY["idastar"] is IDAStarAgent
    with pytest.raises(ValueError):
        UCSAgent(objective="c3")
    with pytest.raises(ValueError):
        IDAStarAgent(heuristic="nope")


@pytest.mark.parametrize("objective", ["c1", "c2"])
@pytest.mark.parametrize("preset", ["L0", "L1"])
def test_ucs_matches_exact_oracle(objective, preset):
    """독립 오라클(역방향 Dijkstra)의 최적값과 UCS가 실제로 낸 비용이 같아야 한다."""
    env = make_env(ORDERS, START, preset=preset)
    optimum = exact_remaining_costs(env, objective)[env.state]
    c1, c2 = play(env, UCSAgent(objective=objective))
    assert {"c1": c1, "c2": c2}[objective] == optimum


@pytest.mark.parametrize("objective", ["c1", "c2"])
def test_ucs_equals_astar_cost_but_expands_more(objective):
    """허용 휴리스틱 A*와 비용은 같고, 펼친 노드 수는 UCS가 같거나 많다."""
    results = {}
    for agent in (UCSAgent(objective=objective), AStarAgent(heuristic="mst", objective=objective)):
        env = make_env(ORDERS, START, preset="L1")
        c1, c2 = play(env, agent)
        # 최적화한 목적함수만 같아야 한다. 동점 해가 여러 개라 다른 쪽 값은 다를 수 있다.
        results[agent.name] = ({"c1": c1, "c2": c2}[objective], env.node_counts()[0])
    assert results["ucs"][0] == results["astar"][0]
    assert results["ucs"][1] >= results["astar"][1]


def test_reports_memory_and_plan_length():
    env = make_env(ORDERS, START, preset="L1")
    agent = UCSAgent()
    play(env, agent)
    assert agent.metrics["mem_states"] > 0
    assert agent.metrics["plan_len"] == len(env.actions)


def test_reset_clears_previous_plan():
    env = make_env(ORDERS, START, preset="L1")
    agent = UCSAgent()
    first = play(env, agent)
    assert play(env, agent) == first


def test_deadline_is_respected():
    env = make_env(ORDERS, START, preset="L1")
    agent = UCSAgent()
    agent.reset(env, random.Random(0))
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.reset())


@pytest.mark.parametrize("preset", ["L0", "L1"])
def test_bfs_finds_fewest_actions(preset):
    env = make_env(ORDERS, START, preset=preset)
    optimum = fewest_actions(env)
    play(env, BFSAgent())
    assert len(env.actions) == optimum


@pytest.mark.parametrize("preset", ["L0", "L1"])
def test_bfs_cost_is_never_below_ucs(preset):
    """BFS는 비용을 보지 않으므로 총비용이 UCS(최적)보다 작을 수 없다."""
    costs = {}
    for agent in (UCSAgent(), BFSAgent()):
        env = make_env(ORDERS, START, preset=preset)
        costs[agent.name] = play(env, agent)[0]
    assert costs["bfs"] >= costs["ucs"]


def test_bfs_reports_memory_and_respects_deadline():
    env = make_env(ORDERS, START, preset="L1")
    agent = BFSAgent()
    play(env, agent)
    assert agent.metrics["mem_states"] > 0
    assert agent.metrics["plan_len"] == len(env.actions)
    agent.reset(env, random.Random(0))
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.reset())


@pytest.mark.parametrize("preset", ["L0", "L1"])
def test_dfs_completes_but_is_not_better_than_optimal(preset):
    """DFS는 해를 찾지만 행동 수는 BFS 이상, 총비용은 UCS 이상이다."""
    results = {}
    for agent in (UCSAgent(), BFSAgent(), DFSAgent()):
        env = make_env(ORDERS, START, preset=preset)
        c1, _ = play(env, agent)
        results[agent.name] = (c1, len(env.actions))
    assert results["dfs"][0] >= results["ucs"][0]
    assert results["dfs"][1] >= results["bfs"][1]


def test_dfs_is_deterministic_and_reports_metrics():
    env = make_env(ORDERS, START, preset="L1")
    agent = DFSAgent()
    first = play(env, agent)
    assert play(env, agent) == first
    assert agent.metrics["mem_states"] > 0
    assert agent.metrics["plan_len"] == len(env.actions)
    agent.reset(env, random.Random(0))
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.reset())


SMALL = [("김치", "회사"), ("피자", "학교")]       # IDA*(memo=false)도 금방 끝나는 작은 판
TINY = [("김치", "회사")]                         # IDS(memo=false)도 금방 끝나는 판


@pytest.mark.parametrize("memo", [False, True])
@pytest.mark.parametrize("preset", ["L0", "L1"])
def test_ids_finds_fewest_actions(preset, memo):
    """IDS는 BFS처럼 행동 수 최소 해를 찾는다."""
    orders = TINY if not memo else SMALL
    env = make_env(orders, START, preset=preset)
    optimum = fewest_actions(env)
    play(env, IDSAgent(memo=memo))
    assert len(env.actions) == optimum


@pytest.mark.parametrize("memo", [False, True])
@pytest.mark.parametrize("objective", ["c1", "c2"])
def test_idastar_matches_exact_oracle(objective, memo):
    """허용 휴리스틱을 쓰는 IDA*는 최적 비용을 낸다."""
    orders = SMALL if not memo else ORDERS
    env = make_env(orders, START, preset="L1")
    optimum = exact_remaining_costs(env, objective)[env.state]
    c1, c2 = play(env, IDAStarAgent(memo=memo, objective=objective))
    assert {"c1": c1, "c2": c2}[objective] == optimum


def test_memo_trades_memory_for_nodes():
    """전치표를 켜면 노드수는 줄고 메모리는 는다. 끄면 메모리는 경로 길이 수준이다."""
    stats = {}
    for memo in (False, True):
        env = make_env(TINY, START, preset="L1")
        agent = IDSAgent(memo=memo)
        play(env, agent)
        stats[memo] = (env.node_counts()[0], agent.metrics["mem_states"])
    assert stats[True][0] < stats[False][0]
    assert stats[True][1] > stats[False][1]
    assert stats[False][1] <= len(env.actions) + 1


@pytest.mark.parametrize("cls", [IDSAgent, IDAStarAgent])
def test_iterative_reports_and_deadline(cls):
    env = make_env(SMALL, START, preset="L1")
    agent = cls(memo=True)
    play(env, agent)
    assert agent.metrics["depth"] > 0
    assert agent.metrics["plan_len"] == len(env.actions)
    agent.reset(env, random.Random(0))
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.reset())
