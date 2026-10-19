"""I13: 손으로 답을 계산한 사례 6개. 정답은 주석의 계산대로이며, 팀원이 계산을 검토한다.

비용 표기: Cost(c1, c2)
  c1 = 목적함수 ① 증가분 (이동 행동 1건당 1, 잘못된 행동 +10, 항의 초과 +P)
  c2 = 목적함수 ② 증가분 = (행동 전에 끝나지 않은 주문 수) x (행동에 걸린 시간)
"""
import pytest

from env import Action, State, Cost
from env.rules import NO_COMPLAINT
from env.world import DEST_NAMES
from .helpers import make_env

U, D, L, R, LOAD, DELIVER = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT, Action.LOAD, Action.DELIVER)


# ---------------------------------------------------------------- 1. 벽 부딪힘
def test_1_wall_bump():
    """벽이나 지도 밖으로 가면 제자리, 시간 1, 이동 행동이라 ① +1. 잘못된 행동(+10)이 아니다.
    주문 1건이 안 끝났으므로 c2 = 1 x 1 = 1."""
    cases = [
        ((1, 4), R),   # (1,4)는 오른쪽이 막힌 칸
        ((1, 5), L),   # 반대쪽에서도 막힘
        ((2, 1), D),   # (2,1)은 아래쪽이 막힌 칸
        ((3, 1), U),   # 반대쪽에서도 막힘
        ((0, 0), U),   # 지도 밖
        ((9, 9), R),
    ]
    for start, action in cases:
        env = make_env([("김치", "회사")], start)
        res = env.step(action)
        assert res.obs.pos == start
        assert res.cost == Cost(1, 1)
        assert res.info.kind == "bump"
        assert env.clock == 1


def test_1_legal_actions_exclude_walls():
    env = make_env([("김치", "회사")], (1, 4))
    # 오른쪽은 벽. 싣기·배달은 식당·배달지가 아니라 불가.
    assert env.legal_actions(env.state) == (U, D, L)


# ---------------------------------------------------------------- 2. 3종 금지 위반
def test_2_menu_ban_violation_is_wrong_action():
    """김치·피자가 이미 적재된 채 탕수육 식당 (4,8)에서 싣기 -> 3메뉴가 되므로 잘못된 행동.
    시간 1, ① +10, 상태 불변. c2 = 미완료 3 x 1 = 3."""
    orders = [("김치", "회사"), ("피자", "학교"), ("탕수육", "집")]
    env = make_env(orders, (4, 8))                       # 조합 순서: (김치,회사) (피자,학교) (탕수육,집)
    env.state = State((4, 8), (1, 1, 0), NO_COMPLAINT)
    res = env.step(LOAD)
    assert res.info.kind == "wrong"
    assert res.obs == State((4, 8), (1, 1, 0), NO_COMPLAINT)
    assert res.cost == Cost(10, 3)
    assert env.clock == 1 and env.wrong_actions == 1


def test_2_menu_ban_off_or_done_allows_load():
    orders = [("김치", "회사"), ("피자", "학교"), ("탕수육", "집")]
    # 금지 규칙을 끄면(L0) 싣는다: 시간 2, ① 0, c2 = 3 x 2 = 6
    env = make_env(orders, (4, 8), preset="L0")
    env.state = State((4, 8), (1, 1, 0), NO_COMPLAINT)
    res = env.step(LOAD)
    assert res.obs.status == (1, 1, 1) and res.cost == Cost(0, 6) and env.clock == 2
    # 김치가 이미 완료되어 적재 중 메뉴가 피자뿐이면 탕수육을 실어도 2종이라 허용: c2 = 미완료 2 x 2 = 4
    env = make_env(orders, (4, 8))
    env.state = State((4, 8), (2, 1, 0), NO_COMPLAINT)
    res = env.step(LOAD)
    assert res.obs.status == (2, 1, 1) and res.cost == Cost(0, 4)


# ---------------------------------------------------------------- 3. 전부 싣기, 전부 내리기
def test_3_load_all_and_deliver_all():
    """김치 식당 (1,2)에서 시작. 주문: 김치->학교 1, 김치->회사 2, 피자->회사 1 (조합 순서 이 순서).
    LOAD       김치 주문 3건이 한꺼번에 적재. 시간 2, c2 = 4 x 2 = 8                 (시각 2)
    RIGHT      (1,3).  c1 1, c2 = 4 x 1 = 4                                         (시각 3)
    DOWN       (2,3).  c1 1, c2 4                                                   (시각 4)
    DOWN       (3,3)=회사. c1 1, c2 4                                               (시각 5)
    DELIVER    회사행 적재 2건만 내림(피자->회사는 아직 대기). 시간 1, c2 = 4 x 1 = 4  (시각 6)
    합계       ① = 3, ② = 8 + 4 + 4 + 4 + 4 = 24
    검산       완료 2건은 시각 6 -> 12, 미완료 2건은 시각 6까지 각 6 -> 12, 합 24"""
    orders = [("김치", "학교"), ("김치", "회사"), ("김치", "회사"), ("피자", "회사")]
    env = make_env(orders, (1, 2))
    r = env.step(LOAD)
    assert r.obs.status == (1, 1, 0) and r.cost == Cost(0, 8) and env.clock == 2
    for a in (R, D, D):
        r = env.step(a)
        assert r.cost == Cost(1, 4)
    assert env.state.pos == (3, 3)
    r = env.step(DELIVER)
    assert r.obs.status == (1, 2, 0) and r.cost == Cost(0, 4)
    assert env.clock == 6
    assert (env.total_c1, env.total_c2) == (3, 24)
    assert env.sum_done_times == 12
    assert env.total_c2 == env.sum_done_times + env.rules.unfinished(env.state) * env.clock


# ---------------------------------------------------------------- 4. 항의 초과
def test_4_complaint_expires_after_deadline():
    """L2(T=20, P=20). 시각 2에 '집' 항의 발생, 마감 22. 배달원은 (0,0)에서 벽에만 부딪힌다.
    시각 2   슬롯 (1, 집, 20)          마감까지 남은 20
    시각 22  슬롯 (1, 집, 0)           마감 시각이라 아직 유효
    시각 23  마감을 넘김 -> 초과, ① +P(20), 항의 사라짐
    합계     ① = 이동 23 + 초과 20 = 43, ② = 미완료 1 x 23 = 23"""
    env = make_env([("김치", "회사")], (0, 0), complaints=[(2, "집")], preset="L2")
    env.step(U)
    assert env.state.slot == NO_COMPLAINT
    env.step(U)
    assert env.state.slot == (1, 0, 20)
    for _ in range(20):
        env.step(U)
    assert env.clock == 22 and env.state.slot == (1, 0, 0) and env.total_c1 == 22
    r = env.step(U)
    assert r.info.expired == 1 and r.cost == Cost(1 + 20, 1)
    assert env.state.slot == NO_COMPLAINT
    assert (env.total_c1, env.total_c2) == (43, 23)
    assert env.metrics()["score_complaint_miss"] == 1.0


def test_4_arrival_exactly_at_deadline_counts():
    """T=2, 시각 0에 '집' (0,7) 항의, 시작 (0,5). 오른쪽 2번 -> 시각 2(=마감)에 도착: 해소, 벌점 없음."""
    env = make_env([("김치", "회사")], (0, 5), complaints=[(0, "집")], preset="L2", T=2)
    assert env.state.slot == (1, 0, 2)
    env.step(R)
    assert env.state.slot == (1, 0, 1)
    env.step(R)
    assert env.state.pos == (0, 7) and env.state.slot == NO_COMPLAINT
    assert env.total_c1 == 2 and env.expired == 0


def test_4_arrival_one_tick_late_expires():
    """같은 상황에서 T=1이면 마감은 시각 1. 도착은 시각 2라 초과. ① = 이동 2 + P 20 = 22."""
    env = make_env([("김치", "회사")], (0, 5), complaints=[(0, "집")], preset="L2", T=1)
    env.step(R)
    r = env.step(R)
    assert r.info.expired == 1
    assert env.total_c1 == 22


# ---------------------------------------------------------------- 5. 해소 뒤 쉬는 시간
def test_5_cooldown_after_resolution():
    """항의를 일찍 해소해도 다음 추첨은 앞 항의의 마감(t0+T) 다음 시각부터다.
    q=1(추첨하면 반드시 발생)로 두면 쉬는 시간이 보인다. T=20, (0,6)에서 활성 항의 '집' (남은 20)."""
    from dataclasses import replace
    from env import PRESETS, Rules
    p = replace(PRESETS["L2"], q=1.0, T=20)
    rules = Rules(p, [(0, 4, 1)])

    # 오른쪽 한 번 -> (0,7)=집 도착, 남은 19에서 해소. 마감까지 19 시각 동안 쉰다.
    s = State((0, 6), (0,), (1, 0, 20))
    (prob, s, cost), = rules.outcomes(s, R)
    assert prob == 1.0 and s.pos == (0, 7) and s.slot == (2, 19) and cost == Cost(1, 1)

    # 쉬는 동안에는 q=1이어도 새 항의가 없다. (0,7)에서 위로 가면 지도 밖이라 제자리.
    (prob, s, _), = rules.outcomes(s, U)
    assert prob == 1.0 and s.slot == (2, 18)
    s = State((0, 7), (0,), (2, 1))
    (prob, s, _), = rules.outcomes(s, U)
    assert prob == 1.0 and s.slot == NO_COMPLAINT      # 쉬는 시간이 끝난 시각에도 아직 뽑지 않는다

    # 그다음 시각부터 q=1이므로 반드시 발생. 배달지 5곳 균등(각 0.2).
    outs = rules.outcomes(s, U)
    assert len(outs) == 5 and sum(o[0] for o in outs) == pytest.approx(1.0)
    assert all(o[0] == pytest.approx(0.2) for o in outs)
    slots = {o[1].slot for o in outs}
    # 배달원이 (0,7)=집에 있으므로 집 항의는 나타나자마자 해소(쉬는 20), 나머지는 활성(남은 20)
    assert slots == {(2, 20), (1, 1, 20), (1, 2, 20), (1, 3, 20), (1, 4, 20)}


def test_5_cooldown_in_env_and_inconsistent_schedule():
    """실제 판: 시각 0에 집에 이미 있으면 즉시 해소, 쉬는 20 -> 다음 항의는 시각 21부터 가능."""
    env = make_env([("김치", "회사")], (0, 7), complaints=[(0, "집"), (21, "학교")], preset="L2")
    assert env.state.slot == (2, 20)
    for _ in range(20):
        env.step(U)
    assert env.state.slot == NO_COMPLAINT and env.clock == 20
    env.step(U)
    assert env.state.slot[0] == 1 and env.state.slot[1] == 1      # 시각 21에 학교 항의

    # 시각 20에 항의가 있으면 쉬는 시간 규칙과 어긋난 목록이다.
    bad = make_env([("김치", "회사")], (0, 7), complaints=[(0, "집"), (20, "학교")], preset="L2")
    with pytest.raises(RuntimeError):
        for _ in range(21):
            bad.step(U)


# ---------------------------------------------------------------- 6. H에서의 실패 종료
def test_6_horizon_failure():
    """주문을 못 끝내고 시각 500(H)에 도달하면 실패로 끝난다. 미완료 주문은 완료 시각을 H로 친다.
    벽에 500번 부딪힘: ① = 500, ② 평균 = (1건 x 500) / 1건 = 500."""
    env = make_env([("김치", "회사")], (0, 0))
    for i in range(499):
        r = env.step(U)
        assert not r.done
    r = env.step(U)
    assert r.done and not r.success
    m = env.metrics()
    assert m["score_cost"] == 500 and m["score_avg_time"] == 500.0
    assert m["score_success"] is False and m["score_total_time"] == 500
    with pytest.raises(RuntimeError):
        env.step(U)
