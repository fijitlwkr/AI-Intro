"""H=500 경계 테스트 (2026-11-18 팀 확정 규칙).

- 마지막 주문을 시각 500에 배달 완료하면 성공이다. 500까지 못 끝내면 실패다.
- 499에 시작한 싣기(시간 2)는 중간에 자르지 않고 끝까지 처리한다(시계 501). 이후 판은 실패로 끝난다.

판 구성(손계산): 김치 → 회사 주문 1건, 시작 칸 (1,4). (1,4)는 오른쪽이 벽이라 RIGHT가 벽 부딪힘(시간 1, ① +1)이다.
  (1,4) -L-> (1,3) -L-> (1,2)=김치 식당 : 이동 2
  싣기 : 시간 2
  (1,2) -R-> (1,3) -D-> (2,3) -D-> (3,3)=회사 : 이동 3
  배달하기 : 시간 1
부딪힘을 b번 먼저 하면 배달 완료 시각 = b + 2 + 2 + 3 + 1 = b + 8, 싣기 시작 시각 = b + 2.
"""
from env import Action

from .helpers import make_env

U, D, L, R, LOAD, DELIVER = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.LOAD, Action.DELIVER)


def _env_after_bumps(b):
    env = make_env([("김치", "회사")], (1, 4))
    for _ in range(b):
        res = env.step(R)
        assert res.info.kind == "bump" and not res.done
    assert env.clock == b
    return env


def test_h_delivery_exactly_at_500_succeeds():
    """부딪힘 492번 → 배달 완료 시각 500. 성공이고 평균배달시간은 500, ① = 492 + 2 + 3 = 497."""
    env = _env_after_bumps(492)
    for a in (L, L):
        assert not env.step(a).done
    assert env.clock == 494
    assert not env.step(LOAD).done and env.clock == 496
    for a in (R, D, D):
        assert not env.step(a).done
    assert env.clock == 499
    res = env.step(DELIVER)
    assert env.clock == 500
    assert res.done and res.success
    m = env.metrics()
    assert m["score_success"] is True
    assert m["score_avg_time"] == 500.0
    assert m["score_cost"] == 497
    assert m["score_total_time"] == 500


def test_h_load_started_at_499_finishes_at_501_then_fails():
    """부딪힘 497번 + 이동 2 → 시각 499에 싣기 시작. 싣기는 끝까지 처리돼 시계 501, 판은 실패로 끝난다.
    싣기가 끝나도 주문은 적재 상태일 뿐 완료가 아니므로 평균배달시간은 H=500, ① = 497 + 2 = 499."""
    env = _env_after_bumps(497)
    for a in (L, L):
        assert not env.step(a).done
    assert env.clock == 499
    res = env.step(LOAD)
    assert env.clock == 501
    assert res.done and not res.success
    assert res.info.kind != "wrong"
    m = env.metrics()
    assert m["score_success"] is False
    assert m["score_avg_time"] == 500.0
    assert m["score_cost"] == 499
    assert env.state.status == (1,)      # 싣기는 처리됨(적재). 배달은 못 했다.


def test_h_load_ending_exactly_at_500_fails():
    """부딪힘 496번 + 이동 2 → 시각 498에 싣기 시작, 500에 끝난다. 주문 미완료이므로 실패."""
    env = _env_after_bumps(496)
    for a in (L, L):
        assert not env.step(a).done
    assert env.clock == 498
    res = env.step(LOAD)
    assert env.clock == 500
    assert res.done and not res.success
    m = env.metrics()
    assert m["score_avg_time"] == 500.0
    assert m["score_cost"] == 498
