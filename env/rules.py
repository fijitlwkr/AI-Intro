"""게임 규칙. 상태만 보고 다음 상태를 계산하는 순수 함수들이다 (시간 t는 상태에 넣지 않는다).

상태 State
  pos    배달원 위치 (행, 열)
  status 조합별 주문 상태. 조합 순서는 Scenario.combos()와 같고 값은 0 대기, 1 적재, 2 완료
  slot   항의 칸
           (0,)             항의 없음
           (1, 배달지, 남은) 활성 항의. 남은 = 마감 시각 - 지금 시각. 0이어도 도착하면 인정
           (2, 남은)         해소 또는 초과 뒤 쉬는 시간. 남은 시각 동안은 새 항의가 나오지 않는다

시간 규칙: 한 행동은 dt 시간 단위가 걸리고, 시간 단위(tick)마다 항의 칸을 갱신한다.
위치와 주문 변화는 행동이 끝나는 마지막 tick에 적용된다.
"""
from typing import NamedTuple

from .presets import Preset
from .world import (
    Action, MOVES, RESTAURANT_POS, DEST_POS, DEST_NAMES, RESTAURANT_NAMES,
)

WAITING, LOADED, DONE = 0, 1, 2
NO_COMPLAINT = (0,)


class State(NamedTuple):
    pos: tuple
    status: tuple
    slot: tuple


class Cost(NamedTuple):
    """한 번의 행동이 더하는 비용. c1 = 목적함수 ①(총 비용), c2 = 목적함수 ②(완료 시각 합)의 증가분."""
    c1: int
    c2: int


class StepInfo(NamedTuple):
    kind: str       # move, bump(벽), load, deliver, wrong
    dt: int         # 걸린 시간
    expired: int    # 이 행동 중 시간 초과된 항의 수
    arrived: int    # 이 행동 중 새로 나타난 항의 수


def cooldown(left):
    return NO_COMPLAINT if left <= 0 else (2, left)


class Rules:
    def __init__(self, preset: Preset, combos):
        self.preset = preset
        self.combos = tuple(combos)          # ((식당, 배달지, 개수), ...)
        self.counts = tuple(c for _, _, c in self.combos)
        self.n_orders = sum(self.counts)
        self._rest_at = {p: i for i, p in enumerate(RESTAURANT_POS)}
        self._dest_at = {p: i for i, p in enumerate(DEST_POS)}

    # ---------- 기본 조회 ----------
    def initial_state(self, start, first_draw=None):
        """시작 상태. 시간 0의 추첨 결과(first_draw = 배달지 번호 또는 None)를 반영할 수 있다."""
        slot = NO_COMPLAINT
        if first_draw is not None:
            slot = self._arrive(slot, start, first_draw)
        return State(tuple(start), (WAITING,) * len(self.combos), slot)

    def unfinished(self, state):
        return sum(c for c, s in zip(self.counts, state.status) if s != DONE)

    def is_goal(self, state):
        return all(s == DONE for s in state.status)

    # ---------- 결정적인 부분: 위치와 주문 ----------
    def _det(self, state, action):
        """(새 위치, 새 주문 상태, 걸린 시간, ①의 기본 증가분, 종류)."""
        pos, status, _ = state
        p = self.preset
        wrong = (pos, status, 1, p.wrong_penalty, "wrong")
        if action <= Action.RIGHT:
            new = MOVES[pos][action]
            if new is None:
                return (pos, status, 1, 1, "bump")
            return (new, status, 1, 1, "move")
        if action == Action.LOAD:
            r = self._rest_at.get(pos)
            if r is None:
                return wrong
            idx = [i for i, (cr, _, _) in enumerate(self.combos) if cr == r and status[i] == WAITING]
            if not idx:
                return wrong
            if p.menu_ban:
                menus = {self.combos[i][0] for i, s in enumerate(status) if s == LOADED}
                menus.add(r)
                if len(menus) == len(RESTAURANT_NAMES):
                    return wrong
            new = list(status)
            for i in idx:
                new[i] = LOADED
            return (pos, tuple(new), p.load_time, 0, "load")
        if action == Action.DELIVER:
            d = self._dest_at.get(pos)
            if d is None:
                return wrong
            idx = [i for i, (_, cd, _) in enumerate(self.combos) if cd == d and status[i] == LOADED]
            if not idx:
                return wrong
            new = list(status)
            for i in idx:
                new[i] = DONE
            return (pos, tuple(new), p.deliver_time, 0, "deliver")
        raise ValueError(f"알 수 없는 행동: {action}")

    def legal_actions(self, state):
        """효과가 있는 행동만. 벽에 부딪히는 이동과 잘못된 행동은 뺀다 (환경은 6개 모두 받는다)."""
        out = []
        for a in Action:
            kind = self._det(state, a)[4]
            if kind in ("move", "load", "deliver"):
                out.append(a)
        return tuple(out)

    # ---------- 항의 칸 갱신 ----------
    def _arrive(self, slot, pos, dest):
        """배달지 dest에 항의가 나타난다. 배달원이 이미 그 칸이면 바로 해소된다."""
        if pos == DEST_POS[dest]:
            return cooldown(self.preset.T)
        return (1, dest, self.preset.T)

    def _age(self, slot, pos):
        """시간이 1 흐른다. (새 항의 칸, 초과 건수, 이 시각에 새 항의를 뽑을 수 있는가)."""
        kind = slot[0]
        if kind == 0:
            return NO_COMPLAINT, 0, True
        if kind == 1:
            _, dest, left = slot
            left -= 1
            if left < 0:                       # 마감을 넘김: 초과, 같은 시각부터 다시 뽑을 수 있다
                return NO_COMPLAINT, 1, True
            if pos == DEST_POS[dest]:          # 마감 안에 도착: 해소, 마감까지 쉰다
                return cooldown(left), 0, False
            return (1, dest, left), 0, False
        return cooldown(slot[1] - 1), 0, False

    # ---------- 한 단계 진행 ----------
    def step(self, state, action, draw):
        """행동 하나를 적용한다. draw(j) = j번째 tick에 나타나는 항의의 배달지 번호 또는 None.
        draw는 새 항의를 뽑을 수 있는 tick에서만 호출된다. 반환: (다음 상태, Cost, StepInfo)."""
        pos0 = state.pos
        pos1, status1, dt, c1, kind = self._det(state, Action(action))
        c2 = self.unfinished(state) * dt
        slot = state.slot
        expired = arrived = 0
        for j in range(1, dt + 1):
            pos = pos1 if j == dt else pos0
            slot, pen, drawable = self._age(slot, pos)
            expired += pen
            if drawable:
                dest = draw(j)
                if dest is not None:
                    slot = self._arrive(slot, pos, dest)
                    arrived += 1
        c1 += expired * self.preset.P
        return State(pos1, status1, slot), Cost(c1, c2), StepInfo(kind, dt, expired, arrived)

    # ---------- 공용 확률 모델 (I4) ----------
    def outcomes(self, state, action):
        """이 행동 뒤에 일어날 수 있는 경우와 확률의 목록: [(확률, 다음 상태, Cost), ...].
        항의가 새로 나올 수 있는 tick마다 확률 q로 나오고 배달지는 5곳 균등이다. 확률의 합은 1이다."""
        pos0 = state.pos
        pos1, status1, dt, c1, _ = self._det(state, Action(action))
        c2 = self.unfinished(state) * dt
        q, P = self.preset.q, self.preset.P
        merged = {}

        def walk(slot, j, prob, expired):
            if j > dt:
                key = (slot, expired)
                merged[key] = merged.get(key, 0.0) + prob
                return
            pos = pos1 if j == dt else pos0
            slot2, pen, drawable = self._age(slot, pos)
            expired2 = expired + pen
            if drawable and q > 0:
                if q < 1:
                    walk(slot2, j + 1, prob * (1 - q), expired2)
                for d in range(len(DEST_POS)):
                    walk(self._arrive(slot2, pos, d), j + 1, prob * q / len(DEST_POS), expired2)
            else:
                walk(slot2, j + 1, prob, expired2)

        walk(state.slot, 1, 1.0, 0)
        return [
            (prob, State(pos1, status1, slot), Cost(c1 + expired * P, c2))
            for (slot, expired), prob in sorted(merged.items(), key=lambda kv: (kv[0][1], kv[0][0]))
        ]
