"""A*/IDA*에서 재사용할 하한. 미래 항의와 항의 페널티는 완화한다.

constraint는 메뉴별 주문 조합 하나씩을 유지한 작은 패턴 데이터베이스(PDB)다.
나머지 주문과 벽을 없애되 남은 주문의 적재 선후관계와 3종 금지는 유지한다.
실제 경로는 이 완화 문제의 경로로 투영되므로 PDB 값은 실제 비용 이하이다.
"""
from heapq import heappop, heappush
from itertools import product
from math import inf

from env.rules import WAITING, LOADED, DONE
from env.world import RESTAURANT_POS, DEST_POS
from .rule_agent import distances_to

HEURISTICS = ("max_distance", "mst", "constraint", "zero")


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class DeliveryHeuristic:
    def __init__(self, env, name="mst", objective="c1"):
        if name not in HEURISTICS:
            raise ValueError(f"heuristic은 {HEURISTICS} 중 하나여야 한다")
        if objective not in ("c1", "c2"):
            raise ValueError("objective는 c1 또는 c2여야 한다")
        self.env, self.name, self.objective = env, name, objective
        self.cache = {}
        self.pattern = None

    @property
    def records(self):
        return len(self.cache) + (len(self.pattern.values) if self.pattern else 0)

    def __call__(self, state):
        self.env._check_deadline()
        if self.name == "zero":
            return 0
        key = (state.pos, state.status)
        if key not in self.cache:
            value = self._movement(state)
            if self.objective == "c2":
                value = max(value, self._completion(state))
            if self.name == "constraint":
                if self.pattern is None:
                    self.pattern = _PatternDatabase(self.env, self.objective)
                value = max(value, self.pattern.estimate(state))
            self.cache[key] = value
        return self.cache[key]

    def _movement(self, state):
        stops = set()
        for status, (restaurant, dest, _) in zip(state.status, self.env.rules.combos):
            if status != DONE:
                stops.add(DEST_POS[dest])
                if status == WAITING:
                    stops.add(RESTAURANT_POS[restaurant])
        stops.discard(state.pos)
        if self.name == "max_distance":
            return max((distances_to(p)[state.pos] for p in stops), default=0)
        edges = {p: distances_to(p)[state.pos] for p in stops}
        total = 0
        while edges:
            closest = min(edges, key=lambda p: (edges[p], p))
            total += edges.pop(closest)
            for p in edges:
                edges[p] = min(edges[p], distances_to(p)[closest])
        return total

    def _completion(self, state):
        total = 0
        for status, (restaurant, dest, amount) in zip(state.status, self.env.rules.combos):
            if status == DONE:
                continue
            target = DEST_POS[dest]
            remaining = self.env.preset.deliver_time
            if status == WAITING:
                pickup = RESTAURANT_POS[restaurant]
                remaining += (distances_to(pickup)[state.pos] + self.env.preset.load_time
                              + distances_to(target)[pickup])
            else:
                remaining += distances_to(target)[state.pos]
            total += amount * remaining
        return total


class _PatternDatabase:
    """메뉴마다 개수가 가장 많은 조합 하나를 선택한다. 최대 3조합 × 8위치.

    전처리는 최초 휴리스틱 호출 중 실행해 계산시간에 포함한다.
    상태 3^3 × 8 이하에서 역방향 Dijkstra로 남은 정확한 완화 비용을 구한다.
    """
    def __init__(self, env, objective):
        self.env, self.objective = env, objective
        combos = env.rules.combos
        self.indices = tuple(
            max((i for i, combo in enumerate(combos) if combo[0] == restaurant),
                key=lambda i: (combos[i][2], -i))
            for restaurant in sorted({r for r, _, _ in combos})
        )
        self.combos = tuple(combos[i] for i in self.indices)
        self.points = tuple(sorted({p for r, d, _ in self.combos
                                    for p in (RESTAURANT_POS[r], DEST_POS[d])}))
        reverse = {}
        statuses = tuple(product((WAITING, LOADED, DONE), repeat=len(self.combos)))
        for status in statuses:
            env._check_deadline()
            unfinished = sum(c for (_, _, c), s in zip(self.combos, status) if s != DONE)
            for pos in self.points:
                src = (pos, status)
                for target in self.points:
                    if target != pos:
                        distance = manhattan(pos, target)
                        cost = distance if objective == "c1" else unfinished * distance
                        reverse.setdefault((target, status), []).append((src, cost))
                for nxt, duration in self._services(pos, status):
                    cost = 0 if objective == "c1" else unfinished * duration
                    reverse.setdefault((pos, nxt), []).append((src, cost))
        goal = (DONE,) * len(self.combos)
        self.values = {(p, goal): 0 for p in self.points}
        queue = [(0, p, goal) for p in self.points]
        # 처음은 비용이 모두 0이며 위치가 정렬돼 있어 이미 힙이다.
        while queue:
            env._check_deadline()
            cost, pos, status = heappop(queue)
            if cost != self.values[(pos, status)]:
                continue
            for previous, edge in reverse.get((pos, status), ()):
                candidate = cost + edge
                if candidate < self.values.get(previous, inf):
                    self.values[previous] = candidate
                    heappush(queue, (candidate, *previous))

    def _services(self, pos, status):
        loaded = {r for (r, _, _), s in zip(self.combos, status) if s == LOADED}
        for restaurant in {r for r, _, _ in self.combos}:
            if pos != RESTAURANT_POS[restaurant]:
                continue
            if self.env.preset.menu_ban and len(loaded | {restaurant}) == 3:
                continue
            nxt = tuple(LOADED if r == restaurant and s == WAITING else s
                        for (r, _, _), s in zip(self.combos, status))
            if nxt != status:
                yield nxt, self.env.preset.load_time
        for dest in {d for _, d, _ in self.combos}:
            if pos == DEST_POS[dest]:
                nxt = tuple(DONE if d == dest and s == LOADED else s
                            for (_, d, _), s in zip(self.combos, status))
                if nxt != status:
                    yield nxt, self.env.preset.deliver_time

    def estimate(self, state):
        status = tuple(state.status[i] for i in self.indices)
        if all(s == DONE for s in status):
            return 0
        if (state.pos, status) in self.values:
            return self.values[(state.pos, status)]
        unfinished = sum(c for (_, _, c), s in zip(self.combos, status) if s != DONE)
        weight = 1 if self.objective == "c1" else unfinished
        return min(weight * manhattan(state.pos, p) + self.values.get((p, status), inf)
                   for p in self.points)
