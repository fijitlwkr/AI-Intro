"""에이전트 기본 틀. 알고리즘마다 이 클래스를 상속해서 choose_action(obs)를 구현한다.

러너가 판마다 reset(env, rng)를 부르면 지난 판의 계획과 기록을 반드시 비워야 한다.
무작위가 필요하면 self.rng(시나리오 시드로 만든 random.Random)만 쓴다.
"""
REPLAN_MODES = ("never", "on_complaint", "every_step")


class Agent:
    name = "agent"

    def __init__(self, replan="never"):
        if replan not in REPLAN_MODES:
            raise ValueError(f"replan은 {REPLAN_MODES} 중 하나여야 한다")
        self.replan = replan
        self.env = None
        self.rng = None
        self._prev_slot = None

    def reset(self, env, rng):
        self.env = env
        self.rng = rng
        self._prev_slot = None

    def choose_action(self, obs):
        """obs(State)를 받아 행동(Action 또는 0~5)을 돌려준다. 하위 클래스가 구현한다."""
        raise NotImplementedError

    def needs_replan(self, obs):
        """재계획 설정에 따라 지금 계획을 새로 세워야 하는지. 행동을 고를 때마다 한 번씩 호출한다.
        first call은 항상 True(처음 계획). on_complaint는 새 항의가 나타난 단계에서 True."""
        first = self._prev_slot is None
        newly = obs.slot[0] == 1 and (self._prev_slot is None or self._prev_slot[0] != 1)
        self._prev_slot = obs.slot
        if first or self.replan == "every_step":
            return True
        if self.replan == "on_complaint":
            return newly
        return False
