"""탐색용 확률 모델(outcomes)이 실제 진행(step)과 어긋나지 않는지 확인한다.
실제 한 단계의 결과는 항상 모델이 말하는 '일어날 수 있는 경우' 안에 들어 있어야 한다."""
import random

import pytest

from env import DeliveryEnv, generate, Action
from env.rules import Rules


@pytest.mark.parametrize("preset", ["L2", "L3"])
def test_real_step_is_one_of_modeled_outcomes(preset):
    for seed in range(15):
        env = DeliveryEnv(generate(preset, seed))
        rng = random.Random(seed)
        while not env.done:
            s = env.state
            # 합리적인 행동 위주로 섞어서 싣기·배달·항의 상황이 자주 나오게 한다.
            legal = env.legal_actions(s)
            a = legal[int(rng.random() * len(legal))] if rng.random() < 0.9 else Action(int(rng.random() * 6))
            outs = env.outcomes(s, a)
            assert sum(o[0] for o in outs) == pytest.approx(1.0)
            res = env.step(a)
            assert any(o[1] == res.obs and o[2] == res.cost and o[0] > 0 for o in outs), (preset, seed, a)


def test_successors_count_nodes():
    env = DeliveryEnv(generate("L1", 0))
    assert env.node_counts() == (None, None)
    succ = env.successors(env.state)
    env.successors(env.state)
    assert env.nodes_expanded == 2
    assert env.nodes_generated == 2 * sum(len(o) for _, o in succ)
    env.reset()
    assert env.node_counts() == (None, None)
