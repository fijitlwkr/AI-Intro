"""원본 반례 재현과 CSP 수정 제안의 회귀 검사."""
import hashlib
from itertools import permutations
from pathlib import Path
import random

import pytest

from env import Action, ComputeTimeout
from env.world import RESTAURANT_POS, DEST_POS
from tests.helpers import make_env
from verify.csp_candidate import CSPCandidateAgent, CSPPlanError
from verify.fixtures.csp_d9fb289 import CSPAgent

ORDERS = [("김치", "집"), ("피자", "학교"), ("탕수육", "회사")]


def partial_env():
    env = make_env(ORDERS, start=RESTAURANT_POS[2])
    env.state = env.state._replace(status=(1, 1, 0))
    return env


def agent_at(env, cls=CSPCandidateAgent, **kwargs):
    agent = cls(**kwargs)
    agent.reset(env, random.Random(0))
    agent.make_variables(env.state)
    return agent


def test_frozen_original_matches_github_blob():
    path = Path(__file__).resolve().parents[1] / "verify/fixtures/csp_d9fb289.py"
    body = path.read_bytes().replace(b"\r\n", b"\n").rstrip(b"\n")
    expected = "56e412b07f8ab87e2c544da959557dd3b943f592"
    assert any(hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest() == expected
               for b in (body, body + b"\n"))


def test_original_counterexample_and_candidate_fix():
    env = partial_env()
    assert Action.LOAD not in env.legal_actions(env.state)
    assert agent_at(env, CSPAgent).check_menu_ban({"P2": 1}) is True
    assert agent_at(env).check_menu_ban({"P2": 1}) is False


def test_original_really_selects_illegal_load_with_other_two_menus_loaded():
    env = make_env(ORDERS, start=RESTAURANT_POS[0])
    env.state = env.state._replace(status=(0, 1, 1))
    original = agent_at(env, CSPAgent)
    assert original.choose_action(env.state) == Action.LOAD
    assert Action.LOAD not in env.legal_actions(env.state)
    candidate = agent_at(env)
    assert candidate.choose_action(env.state) in env.legal_actions(env.state)
    assert candidate.choose_action(env.state) != Action.LOAD


def test_missing_prefix_does_not_prune_feasible_delivery_then_pickup():
    agent = agent_at(partial_env())
    assert agent.check_menu_ban({"P2": 2})
    assert agent.is_consistent({"D0": 1, "P2": 2})


def public_sequence_legal(env, tasks):
    obs = env.state
    for task in tasks:
        index = int(task[1:])
        pickup = task.startswith("P")
        if (pickup and obs.status[index] != 0) or (not pickup and obs.status[index] == 2):
            continue
        if not pickup and obs.status[index] != 1:
            return False
        restaurant, dest, _ = env.rules.combos[index]
        obs = obs._replace(pos=RESTAURANT_POS[restaurant] if pickup else DEST_POS[dest])
        action = Action.LOAD if pickup else Action.DELIVER
        if action not in env.legal_actions(obs):
            return False
        obs = env.outcomes(obs, action)[0][1]
    return True


@pytest.mark.parametrize("partial", [False, True])
def test_all_task_permutations_match_public_action_legality(partial):
    env = partial_env() if partial else make_env(ORDERS, start=(0, 0))
    agent = agent_at(env)
    variables, _ = agent.make_variables(env.state)
    # 전체 대기 6!=720개, 부분 적재 4!=24개 순서를 모두 확인한다.
    for tasks in permutations(variables):
        assignment = {task: i + 1 for i, task in enumerate(tasks)}
        assert agent.is_consistent(assignment) == public_sequence_legal(env, tasks), tasks


def test_delivering_one_combo_does_not_remove_other_destination_of_same_menu():
    orders = [("김치", "집"), ("김치", "학교"), ("피자", "공원"), ("탕수육", "회사")]
    env = make_env(orders, start=(0, 0))
    env.state = env.state._replace(status=(1, 1, 1, 0))
    agent = agent_at(env)
    assert not agent.check_menu_ban({"D0": 1, "P3": 2})


def test_delivery_batches_all_loaded_orders_at_same_destination():
    env = make_env([("김치", "집"), ("피자", "집"), ("탕수육", "회사")], start=(0, 0))
    env.state = env.state._replace(status=(1, 1, 0))
    agent = agent_at(env)
    assert agent.check_menu_ban({"D0": 1, "P2": 2})
    assert public_sequence_legal(env, ["D0", "P2"])


@pytest.mark.parametrize("fc", [False, True])
@pytest.mark.parametrize("status", [(1, 1, 0), (0, 1, 1)])
def test_partial_state_is_completed_without_wrong_actions(fc, status):
    env = make_env(ORDERS, start=RESTAURANT_POS[status.index(0)])
    env.state = env.state._replace(status=status)
    agent = agent_at(env, fc=fc)
    first = True
    while not env.done:
        action = agent.choose_action(env.state)
        if first:
            assert action != Action.LOAD
            first = False
        assert action in env.legal_actions(env.state)
        env.step(action)
    assert env.success and env.wrong_actions == 0


@pytest.mark.parametrize("mode", ["never", "on_complaint", "every_step"])
def test_replan_setting_is_honored_and_reset_clears_plan(mode):
    env = make_env([("김치", "회사")], start=(1, 2))
    agent = agent_at(env, replan=mode)
    builds = []
    original = agent._build_plan

    def build(obs):
        builds.append(obs)
        return original(obs)

    agent._build_plan = build
    while not env.done:
        env.step(agent.choose_action(env.state))
    expected = len(env.actions) if mode == "every_step" else 1
    assert len(builds) == expected
    assert agent.metrics["replans"] == expected - 1
    env.reset()
    agent.reset(env, random.Random(0))
    assert not agent.plan and not agent._planned


def test_no_solution_raises_instead_of_returning_arbitrary_up(monkeypatch):
    env = partial_env()
    agent = agent_at(env)
    monkeypatch.setattr(agent, "backtrack", lambda *args: None)
    with pytest.raises(CSPPlanError, match="해가 없습니다"):
        agent.choose_action(env.state)


def test_new_complaint_causes_replan_in_on_complaint_mode():
    env = make_env([("김치", "회사")], start=(1, 2), preset="L2", q=0,
                   complaints=[(1, "집")])
    agent = agent_at(env, replan="on_complaint")
    while not env.done:
        env.step(agent.choose_action(env.state))
    assert env.success and env.arrived == 1
    assert agent.metrics["replans"] == 1


def test_deadline_is_checked_in_action_selection_and_backtracking():
    env = partial_env()
    agent = agent_at(env)
    env.set_deadline(0)
    with pytest.raises(ComputeTimeout):
        agent.choose_action(env.state)
    with pytest.raises(ComputeTimeout):
        agent.backtrack({}, [], {})


def test_menu_ban_disabled_accepts_third_menu():
    env = make_env(ORDERS, start=(4, 8), menu_ban=False)
    env.state = env.state._replace(status=(1, 1, 0))
    assert agent_at(env).check_menu_ban({"P2": 1})
