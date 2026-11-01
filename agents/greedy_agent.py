"""Greedy Best-first: 누적 비용 g 없이 h만으로 전체 frontier를 탐색한다.

현재 항의는 전이에 반영하되 미래 신규 항의는 없다고 가정한다.
휴리스틱은 항의 비용과 메뉴 제약을 완화하고, 실제 전이는 3종 금지를 지킨다.
"""
from collections import deque
from heapq import heappop, heappush
from itertools import count

from env import Agent
from env.rules import WAITING, DONE
from env.world import RESTAURANT_POS, DEST_POS
from .rule_agent import distances_to


class GreedyAgent(Agent):
    name = "greedy"

    def __init__(self, replan="never", heuristic="mst", objective="c1"):
        super().__init__(replan)
        if heuristic not in ("max_distance", "mst"):
            raise ValueError("heuristic은 max_distance 또는 mst여야 한다")
        if objective not in ("c1", "c2"):
            raise ValueError("objective는 c1 또는 c2여야 한다")
        self.heuristic = heuristic
        self.objective = objective

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()
        self._movement_cache = {}

    def estimate(self, state):
        """남은 비용의 하한. 전처리도 choose_action 중 수행해 계산 시간에 포함한다."""
        key = (state.pos, state.status)
        if key not in self._movement_cache:
            stops = set()
            for status, (restaurant, dest, _) in zip(state.status, self.env.rules.combos):
                if status != DONE:
                    stops.add(DEST_POS[dest])
                    if status == WAITING:
                        stops.add(RESTAURANT_POS[restaurant])
            stops.discard(state.pos)
            if self.heuristic == "max_distance":
                movement = max((distances_to(p)[state.pos] for p in stops), default=0)
            else:
                # Prim: 실제 경로가 반드시 방문할 위치들을 잇는 MST는 이동 하한이다.
                edges = {p: distances_to(p)[state.pos] for p in stops}
                movement = 0
                while edges:
                    closest = min(edges, key=lambda p: (edges[p], p))
                    movement += edges.pop(closest)
                    for p in edges:
                        edges[p] = min(edges[p], distances_to(p)[closest])
            self._movement_cache[key] = movement
        movement = self._movement_cache[key]
        if self.objective == "c1":
            return movement

        # 완료 시각 합: 각 주문을 독립적으로 즉시 처리할 수 있다고 완화한다.
        completion = 0
        for status, (restaurant, dest, amount) in zip(state.status, self.env.rules.combos):
            if status == DONE:
                continue
            target = DEST_POS[dest]
            remaining = self.env.preset.deliver_time
            if status == WAITING:
                pickup = RESTAURANT_POS[restaurant]
                remaining += (distances_to(pickup)[state.pos]
                              + self.env.preset.load_time + distances_to(target)[pickup])
            else:
                remaining += distances_to(target)[state.pos]
            completion += amount * remaining
        return max(movement, completion)

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError("Greedy 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _search(self, start):
        self._movement_cache.clear()
        serial = count()
        frontier = [(self.estimate(start), next(serial), start)]
        parents = {start: None}
        self._report_memory(frontier, parents)
        while frontier:
            _, _, state = heappop(frontier)
            if self.env.is_goal(state):
                actions = deque()
                while parents[state] is not None:
                    previous, action = parents[state]
                    actions.appendleft(action)
                    state = previous
                self.report("plan_len", len(actions))
                return actions
            for action, outcomes in self.env.successors(state, new_complaints=False):
                _, nxt, _ = outcomes[0]
                if nxt in parents:
                    continue
                parents[nxt] = (state, action)
                # 같은 h는 생성 순서. g, 깊이, 실제 비용은 우선순위에 넣지 않는다.
                heappush(frontier, (self.estimate(nxt), next(serial), nxt))
            self._report_memory(frontier, parents)
        raise RuntimeError("Greedy 탐색에서 배달 완료 경로를 찾지 못했습니다.")

    def _report_memory(self, frontier, parents):
        # 상태 레코드 수로 frontier, 부모 표, 캐시의 항목 수를 합산한다.
        self.report("mem_states", len(frontier) + len(parents) + len(self._movement_cache))
