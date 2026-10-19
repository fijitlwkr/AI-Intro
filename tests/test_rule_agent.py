import random

from agents import REGISTRY
from agents.rule_agent import RuleAgent, distances_to, step_toward
from env import Action, DeliveryEnv, generate
from env.world import MOVES, DEST_POS, RESTAURANT_POS
from runner.play import run_game
from tests.helpers import make_env


def _play(env, agent):
    obs = env.reset()
    agent.reset(env, random.Random(0))
    while not env.done:
        obs = env.step(agent.choose_action(obs)).obs
    return env


def test_registered():
    assert REGISTRY["rule"] is RuleAgent


def test_step_toward_never_bumps_and_shortens_distance():
    for target in DEST_POS + RESTAURANT_POS:
        dist = distances_to(target)
        assert len(dist) == 100                      # 모든 칸에서 도달 가능
        for pos in dist:
            if pos == target:
                continue
            a = step_toward(pos, target)
            nxt = MOVES[pos][a]
            assert nxt is not None and dist[nxt] == dist[pos] - 1


def test_no_wrong_actions_and_finishes_on_all_presets():
    for preset in ("L0", "L1", "L2", "L3"):
        for seed in range(5):
            line = run_game(RuleAgent(), generate_preset(preset, seed))
            assert line["score_success"] is True
            assert line["score_wrong_actions"] == 0
            assert line["compute_nodes_expanded"] is None      # 탐색 함수를 쓰지 않는다


def generate_preset(preset, seed):
    from env import PRESETS
    return generate(PRESETS[preset], seed)


def test_hand_case_single_order_takes_shortest_path():
    # 김치(1,2)에서 시작: 싣고 회사(3,3)로. 이동 수 = 회사까지 최단 거리, 싣기와 배달은 비용 0.
    env = make_env([("김치", "회사")], start=(1, 2), preset="L0")
    _play(env, RuleAgent())
    assert env.success
    assert env.total_c1 == distances_to(DEST_POS[4])[RESTAURANT_POS[0]]
    assert env.wrong_actions == 0


def test_menu_ban_defers_third_restaurant():
    # 김치+피자 주문을 싣고 있으면 탕수육 식당에서 싣지 않고 먼저 배달한다.
    env = make_env([("김치", "집"), ("피자", "학교"), ("탕수육", "회사")], start=(1, 2), preset="L1")
    _play(env, RuleAgent())
    assert env.success and env.wrong_actions == 0


def test_complaint_priority_goes_to_complaint_destination():
    # 항의가 학교(6,4)에 20 안에 나타나면, 우선 설정에서는 기다리는 주문이 있어도 학교로 향한다.
    env = make_env([("김치", "집")], start=(0, 0), complaints=[(0, "학교")], preset="L2", q=0.0)
    obs = env.reset()
    assert obs.slot[0] == 1
    agent = RuleAgent()
    agent.reset(env, random.Random(0))
    a = agent.choose_action(obs)
    assert MOVES[obs.pos][a] is not None
    assert distances_to(DEST_POS[1])[MOVES[obs.pos][a]] == distances_to(DEST_POS[1])[obs.pos] - 1


def test_complaint_ignored_when_priority_off():
    env = make_env([("김치", "집")], start=(0, 0), complaints=[(0, "학교")], preset="L2", q=0.0)
    obs = env.reset()
    agent = RuleAgent(complaint_priority=False)
    agent.reset(env, random.Random(0))
    a = agent.choose_action(obs)
    # 김치 식당 쪽으로 간다
    assert distances_to(RESTAURANT_POS[0])[MOVES[obs.pos][a]] == distances_to(RESTAURANT_POS[0])[obs.pos] - 1


def test_does_not_chase_hopeless_complaint():
    # 남은 시간보다 거리가 먼 항의는 쫓지 않는다. 가까운 일(식당 싣기)을 한다.
    env = make_env([("김치", "집")], start=(1, 2), complaints=[(0, "아파트")], preset="L2", q=0.0, T=3)
    obs = env.reset()
    assert obs.slot == (1, 3, 3)
    agent = RuleAgent()
    agent.reset(env, random.Random(0))
    assert agent.choose_action(obs) == Action.LOAD
