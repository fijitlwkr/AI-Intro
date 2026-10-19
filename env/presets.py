"""난이도 프리셋과 설정값을 한 곳에 모아 둔다. 다른 파일에는 숫자를 직접 쓰지 않는다.

DRAFT 표시는 파일럿 뒤에 바뀔 수 있는 초안 값이다. 바뀌면 시나리오 파일(scenarios/)도 다시 만들어야 한다.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    n: int = 8                      # 주문 수
    q: float = 0.0                  # 시간 단위당 항의 발생 확률 (0이면 항의 없음)
    T: int = 20                     # 항의 제한 시간
    P: int = 20                     # 항의 초과 페널티
    menu_ban: bool = True           # 3종 금지
    ensure_all_menus: bool = True   # 한 판에 3메뉴가 모두 등장하도록 보장
    load_time: int = 2              # 싣기 소요 시간
    deliver_time: int = 1           # 배달하기 소요 시간 (고정)
    wrong_penalty: int = 10         # 잘못된 행동 페널티 (고정)
    horizon: int = 500              # 최대 시간 H (고정)


PRESETS = {
    "L0": Preset("L0", n=8, q=0.0, menu_ban=False),
    "L1": Preset("L1", n=8, q=0.0, menu_ban=True),
    # DRAFT: q, T, P, load_time은 파일럿에서 확정한다.
    "L2": Preset("L2", n=8, q=0.03, T=20, P=20, menu_ban=True, load_time=2),
    # T=15는 확정 값이다. q, P는 DRAFT.
    "L3": Preset("L3", n=12, q=0.06, T=15, P=40, menu_ban=True, load_time=2),
}

DEFAULT_PRESET = "L2"
