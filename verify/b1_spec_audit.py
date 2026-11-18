"""Specification-to-code audit, NOT a clean-room independent simulator.

Expected constants and cases were transcribed from the supplied 2026-11-18 rules.
The author has read env/rules.py; do not use this as independent-simulator evidence.
Run: python -m verify.b1_spec_audit --out logs/runs/20261118/spec_audit.json
"""
import argparse
import ast
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from env import DeliveryEnv
from env.presets import PRESETS
from env.rules import State, Rules
from env.scenario import Scenario, generate
from env import world
from .b_common import metadata

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "verify/fixtures/delivery_game_rules_20261118.txt"


def case(start=(0, 0), orders=((0, 0),), complaints=(), preset="L2"):
    return DeliveryEnv(Scenario("spec-case", preset, 0, (), start, orders, complaints))


def audit():
    checks = []

    def check(name, passed, evidence):
        checks.append({"name": name, "status": "pass" if passed else "fail", "evidence": evidence})

    constants = {
        "GRID": 10,
        "RESTAURANT_POS": ((1, 2), (8, 1), (4, 8)),
        "DEST_POS": ((0, 7), (6, 4), (9, 5), (7, 9), (3, 3)),
        "WALL_RIGHT": frozenset(((0, 4), (1, 4), (2, 4), (5, 5), (6, 5), (7, 5), (2, 8), (3, 8), (8, 2), (9, 2))),
        "WALL_DOWN": frozenset(((2, 0), (2, 1), (2, 2), (4, 5), (4, 6), (4, 7), (6, 7), (6, 8), (7, 2), (7, 3), (0, 5), (0, 6))),
    }
    check("map_constants", all(getattr(world, k) == v for k, v in constants.items()), "All map constants compared to specification section 1")
    seen = {(0, 0)}
    queue = [(0, 0)]
    for pos in queue:
        for nxt in world.MOVES[pos]:
            if nxt is not None and nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    check("map_connected", len(seen) == 100, {"reachable_cells": len(seen)})
    env = case()
    res = env.step(world.Action.UP)
    check("wall_bump", res.obs.pos == (0, 0) and res.cost.c1 == 1 and res.info.dt == 1 and env.wrong_actions == 0, "UP at (0,0): stay, dt=1, c1=1")
    env = case()
    res = env.step(world.Action.LOAD)
    check("wrong_load", res.obs.status == (0,) and res.info.dt == 1 and res.cost.c1 == 10, "LOAD away from restaurant: unchanged, dt=1, c1=10")
    env = case(start=(1, 2), orders=((0, 4), (0, 4), (0, 1), (1, 4)))
    loaded = env.step(world.Action.LOAD)
    env.state = State((3, 3), (1, 1, 1), (0,))  # Synthetic loaded state for batch-delivery boundary.
    delivered = env.step(world.Action.DELIVER)
    check("batch_operations", loaded.obs.status == (1, 1, 0) and loaded.info.dt == 2 and loaded.cost.c1 == 0 and delivered.obs.status == (1, 2, 2) and delivered.info.dt == 1, "LOAD all same restaurant; DELIVER all loaded same destination (including duplicates)")
    env = case(start=(4, 8), orders=((0, 0), (1, 1), (2, 2)))
    env.state = State((4, 8), (1, 1, 0), (0,))
    res = env.step(world.Action.LOAD)
    check("third_menu_rejected", res.obs.status == (1, 1, 0) and res.info.dt == 1 and res.cost.c1 == 10, "No partial pickup or illegal loaded-state transition")
    rules = Rules(PRESETS["L2"], ((0, 0, 1),))
    res, cost, info = rules.step(State((0, 6), (0,), (1, 0, 1)), world.Action.RIGHT, lambda _: None)
    check("inclusive_deadline", res.pos == (0, 7) and res.slot == (0,) and info.expired == 0, "Arrival at remaining=0 solves complaint without DELIVER")
    env = case(start=(0, 7), complaints=((0, 0), (21, 1)))
    immediate = env.state.slot == (2, 20)
    for _ in range(20):
        env.step(world.Action.UP)
    before = env.arrived
    env.step(world.Action.UP)
    check("cooldown_and_immediate_resolution", immediate and before == 1 and env.arrived == 2, "t0=0 resolves immediately; next eligible arrival t=21")
    expected = {"L0": (8, 0, 20, 20, False), "L1": (8, 0, 20, 20, True), "L2": (8, .03, 20, 20, True), "L3": (12, .06, 15, 40, True)}
    check("presets", all((p.n, p.q, p.T, p.P, p.menu_ban) == expected[k] and p.horizon == 500 and p.load_time == 2 and p.deliver_time == 1 and p.wrong_penalty == 10 for k, p in PRESETS.items() if k in expected), "L0-L3 and service times/penalties/H")
    scenarios = [generate(p, seed) for p in expected for seed in range(100)]
    check("scenario_content", all(len(s.orders) == PRESETS[s.preset].n and len({r for r, _ in s.orders}) == 3 and all(b[0] - a[0] > PRESETS[s.preset].T for a, b in zip(s.complaints, s.complaints[1:])) for s in scenarios), "400 generated cases: n, all menus, non-overlapping complaint schedule; distribution tested separately by B2")

    # Reach t=499 at the restaurant by real actions, not by editing clock.
    env = case(start=(1, 2), complaints=((480, 0),))
    for _ in range(498):
        env.step(world.Action.UP)
    env.step(world.Action.DOWN)
    env.step(world.Action.LOAD)
    horizon = {"clock": env.clock, "status": env.state.status, "expired": env.expired,
               "score_cost": env.metrics()["score_cost"], "total_c2": env.total_c2,
               "unfinished_H": env.metrics()["score_avg_time"], "actions": len(env.actions)}
    check("hard_horizon", env.clock <= 500 and env.expired == 0, horizon)

    # Count represented slot values, including remaining=0 required by section 5.
    slots = {(0,)} | {(2, left) for left in range(1, 21)}
    for dest in range(5):
        state = rules.initial_state((0, 0), dest)
        slots.add(state.slot)
        for _ in range(20):
            state, _, _ = rules.step(state, world.Action.UP, lambda _: None)
            slots.add(state.slot)
    check("spec_slot_count", len(slots) == 121, {"spec_claim_T20": 121, "represented_T20": len(slots), "formula": "1 + 5*(T+1) + T = 6*T+6"})

    # Static name access audit is limited; it is not a sandbox/security proof.
    direct_reads = []
    for path in (ROOT / "agents").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in {"scenario", "_schedule", "complaints"}:
                direct_reads.append(f"{path.name}:{node.lineno}:{node.attr}")
    exposed = hasattr(case().scenario, "complaints") and hasattr(case(), "_schedule")
    check("future_schedule_access_control", not exposed, {"accessible_via_env": exposed, "direct_agent_reads_found": direct_reads, "limitation": "Static scan is not proof against indirect access"})

    env = case(start=(0, 7))
    env.clock = 499
    env.state = State((0, 7), (1,), (0,))
    env.step(world.Action.DELIVER)
    return {
        "status": "issues_found" if any(c["status"] == "fail" for c in checks) else "pass",
        "date": "2026-11-18", "spec_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest(),
        "environment": metadata(),
        "scope": "Implementation-informed specification audit; NOT an independent simulator",
        "checks": checks,
        "clarifications": [{"name": "delivery_exactly_at_H", "observed_success": env.success, "clock": env.clock, "question": "Specify whether goal or H-failure has priority at t=500."},
                           {"name": "difficulty_vs_n", "note": "k<=15 is true, but k can increase with n and the order-state factor is 3**k; weak difficulty growth is not guaranteed."}],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = audit()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "pass": sum(c["status"] == "pass" for c in report["checks"]), "issues": [c["name"] for c in report["checks"] if c["status"] == "fail"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
