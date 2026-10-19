from collections import deque

from env import Agent, Action
from env.world import MOVE_ACTIONS, MOVES, RESTAURANT_POS, DEST_POS

LOADED, WAITING = 1, 0

_DIST_CACHE = {}


def distances_to(target):
    """지도 위 모든 칸에서 target까지의 최단 이동 수. 벽을 반영한다. 지도는 고정이라 한 번만 계산한다."""
    if target not in _DIST_CACHE:
        dist = {target: 0}
        queue = deque([target])
        while queue:
            cur = queue.popleft()
            for nxt in MOVES[cur]:
                if nxt is not None and nxt not in dist:
                    dist[nxt] = dist[cur] + 1
                    queue.append(nxt)
        _DIST_CACHE[target] = dist
    return _DIST_CACHE[target]


def step_toward(pos, target):
    """pos에서 target으로 가는 최단 경로의 첫 이동. 같은 거리 후보는 UP, DOWN, LEFT, RIGHT 순."""
    dist = distances_to(target)
    for a in MOVE_ACTIONS:
        nxt = MOVES[pos][a]
        if nxt is not None and dist[nxt] == dist[pos] - 1:
            return a
    raise ValueError(f"{pos}는 이미 {target}이다")


class RuleAgent(Agent):
    """단순규칙기반. 미리 정한 규칙을 위에서부터 보고 처음 맞는 것을 따른다. 탐색도 계획도 하지 않는다.

    1. 항의가 있고 마감 안에 갈 수 있으면 그 배달지로 간다(complaint_priority=True).
       가는 길에 할 일이 이미 칸 위에 있어도, 마감을 넘기지 않을 때만 한다.
    2. 배달지 칸에 내릴 주문이 있으면 DELIVER.
    3. 식당 칸에 싣을 주문이 있고 3종 금지에 걸리지 않으면 LOAD.
    4. 그 밖에는 할 일이 있는 가장 가까운 곳으로 간다.
       할 일 = 적재한 주문의 배달지, 3종 금지에 걸리지 않는 대기 주문의 식당. 거리가 같으면 번호가 앞선 곳.
    """
    name = "rule"

    def __init__(self, replan="never", complaint_priority=True):
        super().__init__(replan)
        self.complaint_priority = complaint_priority

    # ---------- 칸 위에서 할 수 있는 일 ----------
    def _deliverable(self, obs):
        d = self._dest_at(obs.pos)
        return d is not None and any(
            s == LOADED and cd == d for s, (_, cd, _) in zip(obs.status, self.env.rules.combos))

    def _loadable(self, obs, r=None):
        """식당 r(없으면 지금 칸의 식당)에서 싣기가 잘못된 행동이 되지 않는가."""
        if r is None:
            r = self._rest_at(obs.pos)
        if r is None:
            return False
        combos = self.env.rules.combos
        if not any(s == WAITING and cr == r for s, (cr, _, _) in zip(obs.status, combos)):
            return False
        if self.env.preset.menu_ban:
            menus = {cr for s, (cr, _, _) in zip(obs.status, combos) if s == LOADED}
            menus.add(r)
            if len(menus) == len(RESTAURANT_POS):
                return False
        return True

    @staticmethod
    def _rest_at(pos):
        return RESTAURANT_POS.index(pos) if pos in RESTAURANT_POS else None

    @staticmethod
    def _dest_at(pos):
        return DEST_POS.index(pos) if pos in DEST_POS else None

    # ---------- 규칙 ----------
    def choose_action(self, obs):
        p = self.env.preset
        if self.complaint_priority and obs.slot[0] == 1:
            _, dest, left = obs.slot
            target = DEST_POS[dest]
            dist = distances_to(target)[obs.pos]
            if dist <= left:                       # 이미 늦었으면 쫓지 않는다
                if dist == 0:
                    pass                           # 도착은 시간이 흐를 때 처리되므로 일반 규칙으로 넘긴다
                else:
                    if self._deliverable(obs) and dist + p.deliver_time <= left:
                        return Action.DELIVER
                    if self._loadable(obs) and dist + p.load_time <= left:
                        return Action.LOAD
                    return step_toward(obs.pos, target)
        if self._deliverable(obs):
            return Action.DELIVER
        if self._loadable(obs):
            return Action.LOAD
        target = self._nearest_task(obs)
        if target is None:
            return Action.DELIVER                  # 할 일이 없는데 안 끝난 경우는 없다
        return step_toward(obs.pos, target)

    def _nearest_task(self, obs):
        combos = self.env.rules.combos
        cands = []
        for d in sorted({cd for s, (_, cd, _) in zip(obs.status, combos) if s == LOADED}):
            cands.append(DEST_POS[d])
        for r in range(len(RESTAURANT_POS)):
            if self._loadable(obs, r):
                cands.append(RESTAURANT_POS[r])
        cands = [c for c in cands if c != obs.pos]
        if not cands:
            return None
        return min(cands, key=lambda c: distances_to(c)[obs.pos])
