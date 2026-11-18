"""AND-OR 탐색. 몇 걸음 앞까지 내다보고(깊이 제한), 매 스텝 다시 계획한다.

- OR 노드: 내가 행동을 고른다. 값이 가장 작은 행동을 고른다.
- AND 노드: 그 행동 뒤에 일어날 수 있는 경우(항의가 생김/안 생김)를 모두 대비한다.
    chance="worst": 경우 중 가장 나쁜 값을 쓴다 (AND-OR: 최악의 경우까지 대비)
    chance="mean" : 경우마다 확률을 곱해 평균을 쓴다 (Expectimax)
- 깊이가 끝난 상태는 롤아웃으로 평가한다: 그 상태에서 단순규칙기반 정책(항의 무시)으로
  끝까지 시뮬레이션했을 때의 비용. 실제로 달성 가능한 비용이라 방향이 일관된다.
  (남은 비용 추정식만 쓰면 지도 가운데가 유리해져서 위아래만 반복하는 문제가 있었다.)
- 앞으로 올 항의 일정은 읽지 않는다. env.successors()가 주는 확률 모델만 쓴다.
"""
from env import Agent
from .rule_agent import RuleAgent

CHANCE_MODES = ("worst", "mean")
OBJECTIVES = ("c1", "c2")
ROLLOUT_CAP = 600     # 롤아웃이 끝나지 않을 때의 안전장치


class AndOrAgent(Agent):
    name = "andor"

    def __init__(self, replan="never", depth=3, chance="worst", objective="c1"):
        super().__init__(replan)   # 이 에이전트는 설정과 상관없이 매 스텝 다시 탐색한다
        if chance not in CHANCE_MODES:
            raise ValueError(f"chance는 {CHANCE_MODES} 중 하나여야 한다")
        if objective not in OBJECTIVES:
            raise ValueError(f"objective는 {OBJECTIVES} 중 하나여야 한다")
        if not isinstance(depth, int) or depth < 1:
            raise ValueError("depth는 1 이상의 정수여야 한다")
        self.depth, self.chance, self.objective = depth, chance, objective

    def reset(self, env, rng):
        super().reset(env, rng)
        self._base = RuleAgent(complaint_priority=False)   # 롤아웃에서 쓰는 기본 정책
        self._base.reset(env, rng)
        self._succ = {}    # 상태 -> 다음 상태 목록 (판 안에서 재사용)
        self._memo = {}    # (상태, 남은 깊이) -> 값
        self._leaf_cache = {}
        self._deepest = 0

    def choose_action(self, obs):
        self._deepest = 0
        best_action, best_value = None, None
        # 점수가 같으면 싣기·배달하기(비용 0)를 이동보다 먼저 고른다.
        for action, outcomes in sorted(self._successors(obs), key=lambda x: x[0] < 4):
            self._deepest = max(self._deepest, 1)
            value = self._and_value(outcomes, self.depth - 1)
            if best_value is None or value < best_value - 1e-9:   # 같으면 먼저 나온 행동
                best_action, best_value = action, value
        if best_action is None:
            raise RuntimeError("AND-OR: 고를 수 있는 행동이 없습니다.")
        self.report("depth", self._deepest)
        self.report("mem_states", len(self._succ) + len(self._memo) + len(self._leaf_cache))
        return best_action

    def _successors(self, state):
        if state not in self._succ:
            self._succ[state] = self.env.successors(state)
        return self._succ[state]

    def _value(self, state, left):
        """state에서 앞으로 left걸음 더 내다봤을 때의 값 (작을수록 좋음)."""
        if self.env.is_goal(state):
            return 0
        if left == 0:
            return self._rollout(state)
        self._deepest = max(self._deepest, self.depth - left + 1)
        key = (state, left)
        if key not in self._memo:
            best = None
            for _, outcomes in self._successors(state):          # OR: 행동 중 최소
                value = self._and_value(outcomes, left - 1)
                if best is None or value < best:
                    best = value
            self._memo[key] = self._rollout(state) if best is None else best
        return self._memo[key]

    def _and_value(self, outcomes, left):
        """한 행동 뒤에 일어날 수 있는 경우들(AND)을 하나의 값으로 합친다."""
        cost = self.objective
        if self.chance == "worst":
            return max(getattr(c, cost) + self._value(nxt, left) for _, nxt, c in outcomes)
        return sum(p * (getattr(c, cost) + self._value(nxt, left)) for p, nxt, c in outcomes)

    def _rollout(self, state):
        """깊이가 끝난 상태의 값: 기본 정책으로 끝까지 가는 비용(새 항의는 없다고 가정)."""
        if state not in self._leaf_cache:
            rules, total, now = self.env.rules, 0, state
            for _ in range(ROLLOUT_CAP):
                if rules.is_goal(now):
                    break
                self.env._check_deadline()
                now, c, _ = rules.step(now, self._base.choose_action(now), lambda tick: None)
                total += getattr(c, self.objective)
            else:
                total = 10 ** 6
            self._leaf_cache[state] = total
        return self._leaf_cache[state]