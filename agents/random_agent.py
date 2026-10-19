from env import Agent, Action


class RandomAgent(Agent):
    """기준선. 기본은 6개 행동 중 균등하게 고른다(규칙을 모르는 상태). legal_only=True면 가능한 행동만 고른다."""
    name = "random"

    def __init__(self, replan="never", legal_only=False):
        super().__init__(replan)
        self.legal_only = legal_only

    def choose_action(self, obs):
        if self.legal_only:
            acts = self.env.legal_actions(obs)
        else:
            acts = tuple(Action)
        return acts[int(self.rng.random() * len(acts))]
