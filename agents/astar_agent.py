"""A*: f=g+h. 현재 항의만 반영한 결정적 모델에서 계획한다."""
from collections import deque
from heapq import heappop, heappush
from itertools import count
from math import inf

from env import Agent
from .heuristics import DeliveryHeuristic


class AStarAgent(Agent):
    name = "astar"

    def __init__(self, replan="never", heuristic="mst", objective="c1"):
        super().__init__(replan)
        # 잘못된 CLI 설정은 판을 시작하기 전에 거절한다.
        DeliveryHeuristic(None, heuristic, objective)
        self.heuristic, self.objective = heuristic, objective

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()
        self.estimator = DeliveryHeuristic(env, self.heuristic, self.objective)

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError("A* 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _search(self, start):
        self.estimator.cache.clear()
        serial = count()
        h = self.estimator(start)
        # 같은 f는 작은 h, 다음은 생성 순서. 오래된 경로 검사를 위해 g도 보관한다.
        frontier = [(h, h, next(serial), 0, start)]
        best_g = {start: 0}
        parents = {start: None}
        while frontier:
            self.report("mem_states", len(frontier) + len(best_g) + len(parents)
                        + self.estimator.records)
            self.env._check_deadline()
            _, _, _, g, state = heappop(frontier)
            if g != best_g[state]:
                continue
            if self.env.is_goal(state):
                actions = deque()
                while parents[state] is not None:
                    previous, action = parents[state]
                    actions.appendleft(action)
                    state = previous
                self.report("plan_len", len(actions))
                return actions
            for action, outcomes in self.env.successors(state, new_complaints=False):
                _, nxt, cost = outcomes[0]
                candidate = g + getattr(cost, self.objective)
                if candidate >= best_g.get(nxt, inf):
                    continue
                best_g[nxt] = candidate
                parents[nxt] = (state, action)
                h = self.estimator(nxt)
                heappush(frontier, (candidate + h, h, next(serial), candidate, nxt))
        raise RuntimeError("A* 탐색에서 배달 완료 경로를 찾지 못했습니다.")
