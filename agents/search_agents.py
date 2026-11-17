"""정보 없는 탐색 (담당: 서지민). 현재 항의만 반영한 결정적 모델에서 계획한다.

UCS: g(누적 비용)가 가장 작은 상태부터 펼친다. 휴리스틱이 없는 A*와 같고,
     다른 알고리즘의 최적격차 기준 해가 된다 (L0·L1).
BFS: 얕은 상태(행동 수가 적은 상태)부터 펼친다. 비용은 보지 않으므로
     행동 수 최소 해를 찾고, 비용이 균일하지 않은 이 게임에서는 최적이 깨질 수 있다.
DFS: 가장 최근에 만든 상태부터 깊게 펼친다. 처음 찾은 해를 그대로 쓰므로 최적이 아니고,
     계획이 매우 길어질 수 있다.
IDS: 깊이 제한 DFS를 깊이 0, 1, 2, ...로 늘려 가며 반복한다. 행동 수 최소 해(BFS와 같은 해)를 찾는다.
IDA*: IDS의 깊이 대신 f = g + h 상한을 늘려 가며 반복한다. 휴리스틱은 A*의 DeliveryHeuristic을 재사용한다.

두 반복 심화 탐색은 memo 설정으로 메모리 사용 방식을 고른다.
  memo=false  교과서 방식. 현재 경로만 기억한다 (같은 경로 안의 반복 상태만 막는다). 메모리는 작지만
              같은 상태를 여러 경로로 다시 펼쳐 시간이 폭발한다.
  memo=true   반복마다 "이 상태를 얼마나 좋은 조건으로 이미 봤는지" 표를 둔다 (전치표). 시간은 크게 줄지만
              표 크기만큼 메모리를 쓴다.
"""
from collections import deque
from heapq import heappop, heappush
from itertools import count
from math import inf

from env import Agent
from .heuristics import DeliveryHeuristic

OBJECTIVES = ("c1", "c2")   # c1 = ① 총비용, c2 = ② 완료 시각 합


def build_plan(parents, state):
    """목표 상태에서 부모를 따라 올라가 행동 목록을 만든다."""
    actions = deque()
    while parents[state] is not None:
        state, action = parents[state]
        actions.appendleft(action)
    return actions


class UCSAgent(Agent):
    name = "ucs"

    def __init__(self, replan="never", objective="c1"):
        super().__init__(replan)
        if objective not in OBJECTIVES:
            raise ValueError(f"objective는 {OBJECTIVES} 중 하나여야 한다")
        self.objective = objective

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError("UCS 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _search(self, start):
        serial = count()                        # 같은 g면 먼저 넣은 상태부터 (결과 재현용)
        frontier = [(0, next(serial), start)]
        best_g = {start: 0}
        parents = {start: None}
        while frontier:
            self.report("mem_states", len(frontier) + len(best_g))
            self.env._check_deadline()
            g, _, state = heappop(frontier)
            if g != best_g[state]:              # 더 싼 경로가 이미 나온 오래된 항목
                continue
            if self.env.is_goal(state):         # 꺼낼 때 목표 검사해야 최적이 보장된다
                plan = build_plan(parents, state)
                self.report("plan_len", len(plan))
                return plan
            for action, outcomes in self.env.successors(state, new_complaints=False):
                _, nxt, cost = outcomes[0]
                candidate = g + getattr(cost, self.objective)
                if candidate >= best_g.get(nxt, inf):
                    continue
                best_g[nxt] = candidate
                parents[nxt] = (state, action)
                heappush(frontier, (candidate, next(serial), nxt))
        raise RuntimeError("UCS 탐색에서 배달 완료 경로를 찾지 못했습니다.")


class BFSAgent(Agent):
    name = "bfs"

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError("BFS 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _search(self, start):
        if self.env.is_goal(start):
            return deque()
        frontier = deque([start])               # FIFO 큐: 먼저 들어온 상태부터
        parents = {start: None}                 # 한 번 본 상태는 다시 넣지 않는다 (그래프 탐색)
        while frontier:
            self.report("mem_states", len(frontier) + len(parents))
            self.env._check_deadline()
            state = frontier.popleft()
            for action, outcomes in self.env.successors(state, new_complaints=False):
                _, nxt, _ = outcomes[0]
                if nxt in parents:
                    continue
                parents[nxt] = (state, action)
                if self.env.is_goal(nxt):       # 만들 때 목표 검사: 행동 수 기준 최소는 그대로 보장된다
                    plan = build_plan(parents, nxt)
                    self.report("plan_len", len(plan))
                    return plan
                frontier.append(nxt)
        raise RuntimeError("BFS 탐색에서 배달 완료 경로를 찾지 못했습니다.")


class DFSAgent(Agent):
    name = "dfs"

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError("DFS 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _search(self, start):
        if self.env.is_goal(start):
            return deque()
        frontier = [start]                      # 스택(LIFO): 가장 최근에 넣은 상태부터
        parents = {start: None}                 # 한 번 본 상태는 다시 넣지 않는다 (그래프 탐색, 무한 루프 방지)
        while frontier:
            self.report("mem_states", len(frontier) + len(parents))
            self.env._check_deadline()
            state = frontier.pop()
            for action, outcomes in self.env.successors(state, new_complaints=False):
                _, nxt, _ = outcomes[0]
                if nxt in parents:
                    continue
                parents[nxt] = (state, action)
                if self.env.is_goal(nxt):
                    plan = build_plan(parents, nxt)
                    self.report("plan_len", len(plan))
                    return plan
                frontier.append(nxt)
        raise RuntimeError("DFS 탐색에서 배달 완료 경로를 찾지 못했습니다.")


class _IterativeAgent(Agent):
    """IDS/IDA* 공통 틀: 상한을 늘려 가며 깊이 우선 탐색을 반복한다."""

    def __init__(self, replan="never", memo=False):
        super().__init__(replan)
        self.memo = memo

    def reset(self, env, rng):
        super().reset(env, rng)
        self._plan = deque()

    def choose_action(self, obs):
        if self.needs_replan(obs):
            self._plan = self._search(obs)
        if not self._plan:
            raise RuntimeError(f"{self.name} 계획이 비어 있습니다. 목표 상태 또는 도달 가능성을 확인하세요.")
        return self._plan.popleft()

    def _memory(self):
        """동시에 들고 있는 상태 수: 현재 경로 + 전치표 (+ 휴리스틱 캐시)."""
        return len(self._path) + (len(self._table) if self._table is not None else 0)

    def _finish(self):
        plan = deque(self._actions)
        self.report("plan_len", len(plan))
        return plan


class IDSAgent(_IterativeAgent):
    name = "ids"

    def _search(self, start):
        self._path, self._actions = {start}, []
        limit = 0
        while True:
            self._table = {} if self.memo else None
            self._cutoff = False
            if self._dls(start, limit):
                return self._finish()
            if not self._cutoff:                    # 더 깊이 가도 새 상태가 없다
                raise RuntimeError("IDS 탐색에서 배달 완료 경로를 찾지 못했습니다.")
            limit += 1
            self.report("depth", limit)

    def _dls(self, state, left):
        """남은 깊이 left 안에서 목표를 찾으면 True. self._actions에 경로가 남는다."""
        if self.env.is_goal(state):
            return True
        if left == 0:
            self._cutoff = True
            return False
        self.report("mem_states", self._memory())
        for action, outcomes in self.env.successors(state, new_complaints=False):
            _, nxt, _ = outcomes[0]
            if nxt in self._path:                   # 같은 경로 안에서 되돌아가기 방지
                continue
            if self._table is not None:
                if self._table.get(nxt, -1) >= left - 1:   # 이미 더 많은 남은 깊이로 봤다
                    continue
                self._table[nxt] = left - 1
            self._path.add(nxt)
            self._actions.append(action)
            if self._dls(nxt, left - 1):
                return True
            self._actions.pop()
            self._path.discard(nxt)
        return False


class IDAStarAgent(_IterativeAgent):
    name = "idastar"

    def __init__(self, replan="never", memo=False, heuristic="mst", objective="c1"):
        super().__init__(replan, memo)
        DeliveryHeuristic(None, heuristic, objective)   # 잘못된 설정은 판 시작 전에 거절
        self.heuristic, self.objective = heuristic, objective

    def reset(self, env, rng):
        super().reset(env, rng)
        self.estimator = DeliveryHeuristic(env, self.heuristic, self.objective)

    def _memory(self):
        return super()._memory() + self.estimator.records

    def _search(self, start):
        self.estimator.cache.clear()
        self._path, self._actions = {start}, []
        bound = self.estimator(start)
        while True:
            self._table = {} if self.memo else None
            self._next = inf
            if self._dfs(start, 0, bound):
                return self._finish()
            if self._next == inf:
                raise RuntimeError("IDA* 탐색에서 배달 완료 경로를 찾지 못했습니다.")
            bound = self._next                      # 이번에 넘친 f 중 가장 작은 값으로 상한을 올린다
            self.report("depth", bound)

    def _dfs(self, state, g, bound):
        f = g + self.estimator(state)
        if f > bound:
            self._next = min(self._next, f)
            return False
        if self.env.is_goal(state):
            return True
        self.report("mem_states", self._memory())
        for action, outcomes in self.env.successors(state, new_complaints=False):
            _, nxt, cost = outcomes[0]
            if nxt in self._path:
                continue
            g2 = g + getattr(cost, self.objective)
            if self._table is not None:
                if self._table.get(nxt, inf) <= g2:        # 이미 같거나 더 싼 g로 봤다
                    continue
                self._table[nxt] = g2
            self._path.add(nxt)
            self._actions.append(action)
            if self._dfs(nxt, g2, bound):
                return True
            self._actions.pop()
            self._path.discard(nxt)
        return False
