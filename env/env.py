"""한 판을 진행하는 환경. 두 가지 쓰임새를 한 객체에 담는다.

  탐색용: legal_actions(state), successors(state)  -> 상태만 보고 미리 계산해 본다 (노드 수를 자동으로 센다)
  진행용: reset(), step(action)                    -> 실제 한 판을 진행한다

실제 판에서 항의는 시나리오의 고정 목록대로 나타난다. 알고리즘은 현재 항의(상태의 slot)만 볼 수 있다.
"""
import time

from .presets import PRESETS
from .rules import Rules, State, Cost, StepInfo
from .world import Action


class ComputeTimeout(Exception):
    """행동을 고르는 데 쓸 수 있는 시간을 넘겼다 (러너가 시간 초과 실패로 기록한다)."""


class StepResult:
    __slots__ = ("obs", "cost", "done", "success", "info")

    def __init__(self, obs, cost, done, success, info):
        self.obs, self.cost, self.done, self.success, self.info = obs, cost, done, success, info


class DeliveryEnv:
    def __init__(self, scenario, preset=None):
        if preset is None:
            preset = PRESETS[scenario.preset]
        self.scenario = scenario
        self.preset = preset
        self.rules = Rules(preset, scenario.combos())
        self._schedule = dict(scenario.complaints)
        self._deadline = None
        self.reset()

    # ---------- 시간 제한 (러너가 설정) ----------
    def set_deadline(self, perf_counter_value):
        """이 시각(time.perf_counter 기준)이 지나면 탐색용 함수가 ComputeTimeout을 낸다. None이면 제한 없음."""
        self._deadline = perf_counter_value

    def _check_deadline(self):
        if self._deadline is not None and time.perf_counter() > self._deadline:
            raise ComputeTimeout()

    # ---------- 탐색용 ----------
    def legal_actions(self, state):
        self._check_deadline()
        return self.rules.legal_actions(state)

    def successors(self, state):
        """[(행동, [(확률, 다음 상태, Cost), ...]), ...]. 호출 한 번이 expanded 1, 돌려준 경우의 수가 generated."""
        self._check_deadline()
        out = []
        for a in self.rules.legal_actions(state):
            out.append((a, self.rules.outcomes(state, a)))
        self.nodes_expanded += 1
        self.nodes_generated += sum(len(o) for _, o in out)
        self.successor_calls += 1
        return out

    def outcomes(self, state, action):
        """공용 확률 모델 함수 (I4). 노드 수에는 세지 않는다."""
        self._check_deadline()
        return self.rules.outcomes(state, action)

    def is_goal(self, state):
        return self.rules.is_goal(state)

    # ---------- 진행용 ----------
    def reset(self):
        self.clock = 0
        self.nodes_expanded = 0
        self.nodes_generated = 0
        self.successor_calls = 0
        self.total_c1 = 0
        self.total_c2 = 0
        self.sum_done_times = 0       # 완료된 주문의 완료 시각 합
        self.wrong_actions = 0
        self.expired = 0
        self.arrived = 0
        self.actions = []
        self.done = False
        self.success = False
        first = self._schedule.get(0)
        self.state = self.rules.initial_state(self.scenario.start, first)
        self.arrived += 1 if first is not None else 0
        return self.state

    def step(self, action):
        if self.done:
            raise RuntimeError("이미 끝난 판이다. reset()을 먼저 호출해야 한다.")
        clock0 = self.clock
        used = set()

        def draw(j):
            t = clock0 + j
            used.add(t)
            return self._schedule.get(t)

        unfinished0 = self.rules.unfinished(self.state)
        nxt, cost, info = self.rules.step(self.state, action, draw)
        due = {t for t in self._schedule if clock0 < t <= clock0 + info.dt}
        if due - used:
            raise RuntimeError(f"시나리오 {self.scenario.scenario_id}의 항의 시각 {sorted(due - used)}이(가) "
                               "항의를 받을 수 없는 시점이다. 항의 목록이 규칙과 맞지 않는다.")
        self.state = nxt
        self.clock += info.dt
        self.total_c1 += cost.c1
        self.total_c2 += cost.c2
        self.expired += info.expired
        self.arrived += info.arrived
        self.wrong_actions += 1 if info.kind == "wrong" else 0
        self.sum_done_times += (unfinished0 - self.rules.unfinished(nxt)) * self.clock
        self.actions.append(int(action))
        if self.rules.is_goal(nxt):
            self.done, self.success = True, True
        elif self.clock >= self.preset.horizon:
            self.done, self.success = True, False
        return StepResult(nxt, cost, self.done, self.success, info)

    # ---------- 결과 ----------
    def metrics(self):
        """성과 지표(score_*). 못 끝낸 주문은 완료 시각을 H로 계산한다."""
        unfinished = self.rules.unfinished(self.state)
        avg = (self.sum_done_times + unfinished * self.preset.horizon) / self.rules.n_orders
        return {
            "score_cost": self.total_c1,
            "score_avg_time": avg,
            "score_success": self.success,
            "score_complaint_miss": (self.expired / self.arrived) if self.arrived else None,
            "score_total_time": self.clock,
            "score_wrong_actions": self.wrong_actions,
            "score_complaints": self.arrived,
            "score_expired": self.expired,
        }

    def node_counts(self):
        """탐색용 함수를 한 번도 쓰지 않았으면 (None, None)."""
        if self.successor_calls == 0:
            return None, None
        return self.nodes_expanded, self.nodes_generated
