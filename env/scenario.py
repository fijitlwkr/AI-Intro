"""시나리오 = 한 판의 입력. 주문, 배달원 시작 위치, 항의 고정 목록.

지도와 설정값(q, T, P ...)은 들어 있지 않다. 다만 항의 목록은 q와 T로 만들어지므로
시나리오 파일은 (프리셋, 시드)마다 하나씩 있다. 설정값이 바뀌면 파일을 다시 만들어야 한다.
"""
import json
import random
from dataclasses import dataclass
from pathlib import Path

from .presets import Preset, PRESETS
from .world import GRID, RESTAURANT_NAMES, DEST_NAMES

SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _randint(rng, k):
    """0..k-1. random()만 써서 Python 버전이 달라도 같은 값이 나오게 한다."""
    return int(rng.random() * k)


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    preset: str
    seed: int
    params: tuple        # ((키, 값), ...) 시나리오를 만들 때 쓴 설정값
    start: tuple         # (행, 열)
    orders: tuple        # ((식당 번호, 배달지 번호), ...) 주문 순서대로
    complaints: tuple    # ((발생 시각, 배달지 번호), ...) 발생 시각 오름차순

    def combos(self):
        """((식당, 배달지, 개수), ...) 식당, 배달지 순으로 정렬. 상태의 주문 칸 순서가 된다."""
        counts = {}
        for o in self.orders:
            counts[o] = counts.get(o, 0) + 1
        return tuple((r, d, c) for (r, d), c in sorted(counts.items()))

    def to_json(self):
        return {
            "scenario_id": self.scenario_id,
            "preset": self.preset,
            "seed": self.seed,
            "params": dict(self.params),
            "start": list(self.start),
            "orders": [{"from": RESTAURANT_NAMES[r], "to": DEST_NAMES[d]} for r, d in self.orders],
            "complaints": [{"t": t, "dest": DEST_NAMES[d]} for t, d in self.complaints],
        }

    @staticmethod
    def from_json(data):
        r_idx = {n: i for i, n in enumerate(RESTAURANT_NAMES)}
        d_idx = {n: i for i, n in enumerate(DEST_NAMES)}
        return Scenario(
            scenario_id=data["scenario_id"],
            preset=data["preset"],
            seed=data["seed"],
            params=tuple(sorted(data["params"].items())),
            start=tuple(data["start"]),
            orders=tuple((r_idx[o["from"]], d_idx[o["to"]]) for o in data["orders"]),
            complaints=tuple((c["t"], d_idx[c["dest"]]) for c in data["complaints"]),
        )


def _params_of(preset):
    return tuple(sorted({
        "n": preset.n, "q": preset.q, "T": preset.T,
        "ensure_all_menus": preset.ensure_all_menus, "horizon": preset.horizon,
    }.items()))


def generate(preset, seed):
    """프리셋과 시드로 시나리오를 만든다. 같은 입력이면 항상 같은 결과다."""
    if isinstance(preset, str):
        preset = PRESETS[preset]
    if preset.ensure_all_menus and preset.n < len(RESTAURANT_NAMES):
        raise ValueError("ensure_all_menus는 주문 수 n이 3 이상이어야 한다")
    rng = random.Random(seed)
    start = (_randint(rng, GRID), _randint(rng, GRID))

    while True:
        orders = tuple(
            (_randint(rng, len(RESTAURANT_NAMES)), _randint(rng, len(DEST_NAMES)))
            for _ in range(preset.n)
        )
        if not preset.ensure_all_menus or len({r for r, _ in orders}) == len(RESTAURANT_NAMES):
            break

    # 항의: 시간 0부터 매 시간 단위마다 확률 q로 발생 여부를 뽑는다.
    # 발생하면 다음 추첨은 마감 시각(t0+T) 다음 시각부터 다시 시작한다.
    complaints = []
    if preset.q > 0:
        t = 0
        while t < preset.horizon:
            if rng.random() < preset.q:
                complaints.append((t, _randint(rng, len(DEST_NAMES))))
                t += preset.T + 1
            else:
                t += 1

    return Scenario(
        scenario_id=f"{preset.name}-{seed:03d}",
        preset=preset.name,
        seed=seed,
        params=_params_of(preset),
        start=start,
        orders=orders,
        complaints=tuple(complaints),
    )


def scenario_path(preset_name, seed, directory=None):
    return Path(directory or SCENARIO_DIR) / f"{preset_name}_{seed:03d}.json"


def save(scenario, directory=None):
    path = scenario_path(scenario.preset, scenario.seed, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = scenario.to_json()
    # 키마다 한 줄. 파일이 작고 사람이 읽기 쉽다.
    body = ",\n".join(f" {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in data.items())
    path.write_text("{\n" + body + "\n}\n", encoding="utf-8")
    return path


def load(path):
    return Scenario.from_json(json.loads(Path(path).read_text(encoding="utf-8")))


def check_matches_preset(scenario, preset):
    """파일에 기록된 설정값이 지금 프리셋과 같은지 확인한다. 다르면 파일이 오래된 것이다."""
    if isinstance(preset, str):
        preset = PRESETS[preset]
    if dict(scenario.params) != dict(_params_of(preset)):
        raise ValueError(
            f"{scenario.scenario_id}: 시나리오 파일의 설정값 {dict(scenario.params)}이(가) "
            f"현재 프리셋 {dict(_params_of(preset))}과(와) 다르다. "
            "python -m runner.make_scenarios 로 다시 만들어야 한다."
        )


def load_for(preset_name, seed, directory=None):
    """저장된 파일이 있으면 읽고(설정값 확인), 없으면 (False, 즉석 생성)으로 알려 준다."""
    path = scenario_path(preset_name, seed, directory)
    preset = PRESETS[preset_name]
    if path.exists():
        sc = load(path)
        check_matches_preset(sc, preset)
        return sc, True
    return generate(preset, seed), False
