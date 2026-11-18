"""Expectimax. AND-OR 에이전트와 같은 탐색이고, 항의가 생기는 경우들을 확률로 평균낸다."""
from .andor_agent import AndOrAgent


class ExpectimaxAgent(AndOrAgent):
    name = "expectimax"

    def __init__(self, replan="never", depth=3, objective="c1"):
        super().__init__(replan=replan, depth=depth, chance="mean", objective=objective)