"""고정 지도와 행동 정의. 모든 판에서 같은 값이라 시나리오 파일에 넣지 않는다.

좌표는 (행, 열), 0부터 시작, 맨 위 왼쪽이 (0, 0). 값은 룰 명세 v0.2 §1 기준.
"""
from enum import IntEnum

GRID = 10

# 식당 = 메뉴. 인덱스가 곧 메뉴 번호다.
RESTAURANT_NAMES = ("김치", "피자", "탕수육")
RESTAURANT_POS = ((1, 2), (8, 1), (4, 8))

DEST_NAMES = ("집", "학교", "공원", "아파트", "회사")
DEST_POS = ((0, 7), (6, 4), (9, 5), (7, 9), (3, 3))

# 오른쪽이 막힌 칸: (r, c)에서 오른쪽으로 갈 수 없고, (r, c+1)에서 왼쪽으로도 갈 수 없다.
WALL_RIGHT = frozenset({
    (0, 4), (1, 4), (2, 4), (5, 5), (6, 5), (7, 5), (2, 8), (3, 8), (8, 2), (9, 2),
})
# 아래쪽이 막힌 칸: (r, c)에서 아래로 갈 수 없고, (r+1, c)에서 위로도 갈 수 없다.
WALL_DOWN = frozenset({
    (2, 0), (2, 1), (2, 2), (4, 5), (4, 6), (4, 7), (6, 7), (6, 8), (7, 2), (7, 3), (0, 5), (0, 6),
})


class Action(IntEnum):
    UP = 0
    DOWN = 1
    LEFT = 2
    RIGHT = 3
    LOAD = 4
    DELIVER = 5


MOVE_ACTIONS = (Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT)
_DELTA = {Action.UP: (-1, 0), Action.DOWN: (1, 0), Action.LEFT: (0, -1), Action.RIGHT: (0, 1)}


def _next_pos(pos, action):
    """이동 결과 칸. 벽이거나 지도 밖이면 None."""
    r, c = pos
    dr, dc = _DELTA[action]
    nr, nc = r + dr, c + dc
    if not (0 <= nr < GRID and 0 <= nc < GRID):
        return None
    if action == Action.RIGHT and (r, c) in WALL_RIGHT:
        return None
    if action == Action.LEFT and (nr, nc) in WALL_RIGHT:
        return None
    if action == Action.DOWN and (r, c) in WALL_DOWN:
        return None
    if action == Action.UP and (nr, nc) in WALL_DOWN:
        return None
    return (nr, nc)


# MOVES[pos][action] = 다음 칸 또는 None(막힘)
MOVES = {
    (r, c): tuple(_next_pos((r, c), a) for a in MOVE_ACTIONS)
    for r in range(GRID) for c in range(GRID)
}
