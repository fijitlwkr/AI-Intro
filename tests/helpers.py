from dataclasses import replace

from env import DeliveryEnv, PRESETS, Scenario
from env.world import RESTAURANT_NAMES, DEST_NAMES


def make_env(orders, start, complaints=(), preset="L1", **overrides):
    """손으로 만든 판. orders = [("김치", "회사"), ...], complaints = [(발생 시각, "집"), ...]."""
    p = replace(PRESETS[preset], **overrides) if overrides else PRESETS[preset]
    sc = Scenario(
        scenario_id="hand", preset=p.name, seed=0, params=(),
        start=tuple(start),
        orders=tuple((RESTAURANT_NAMES.index(r), DEST_NAMES.index(d)) for r, d in orders),
        complaints=tuple((t, DEST_NAMES.index(d)) for t, d in complaints),
    )
    return DeliveryEnv(sc, p)
