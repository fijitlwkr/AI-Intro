"""한 판을 돌리고 로그 한 줄(dict)을 만든다."""
import random
import time
from dataclasses import asdict

from env import DeliveryEnv, ComputeTimeout, REPORT_FIELDS, PRESETS

SCHEMA_VERSION = 2   # 1 -> 2: params, preset_params, git_commit, 특성 지표 칸(compute_*) 추가
TIME_LIMIT_SEC = 60.0   # I10: 한 판당 계산 시간 제한. 파일럿 뒤 조정한다.


def run_game(agent, scenario, time_limit=TIME_LIMIT_SEC, run_id=None, params=None, git_commit=None):
    env = DeliveryEnv(scenario)
    obs = env.reset()
    agent.reset(env, random.Random(scenario.seed))

    used = 0.0            # 행동 고르기에 쓴 시간 (환경이 행동을 처리하는 시간은 넣지 않는다)
    failure = None
    while not env.done:
        env.set_deadline(time.perf_counter() + (time_limit - used))
        t0 = time.perf_counter()
        try:
            action = agent.choose_action(obs)
        except ComputeTimeout:
            failure = "timeout"
            used = time.perf_counter() - t0 + used
            break
        used += time.perf_counter() - t0
        if used > time_limit:
            failure = "timeout"
            break
        obs = env.step(action).obs
    env.set_deadline(None)

    if failure is None and not env.success:
        failure = "horizon"       # 최대 시간 H에 도달
    expanded, generated = env.node_counts()
    line = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "algorithm": agent.name,
        "replan": agent.replan,
        "params": dict(params or {}),                    # 알고리즘 설정(휴리스틱 종류 등). 변형끼리 구분하는 데 쓴다
        "preset": scenario.preset,
        "preset_params": asdict(PRESETS[scenario.preset]),   # 돌린 시점의 프리셋 값. [초안] 값이 바뀐 걸 알아보는 데 쓴다
        "seed": scenario.seed,
        "scenario_id": scenario.scenario_id,
        "git_commit": git_commit,
    }
    line.update(env.metrics())
    if failure == "timeout":
        line["score_success"] = False
    line.update({
        "failure": failure,
        "compute_sec": used,
        "compute_nodes_expanded": expanded,
        "compute_nodes_generated": generated,
    })
    for name, (_, field, _) in REPORT_FIELDS.items():     # 알리지 않은 특성 지표는 null
        line[field] = agent.metrics.get(name)
    line["actions"] = env.actions
    return line
