"""에이전트 기본 틀. 알고리즘마다 이 클래스를 상속해서 choose_action(obs)를 구현한다.

러너가 판마다 reset(env, rng)를 부르면 지난 판의 계획과 기록을 반드시 비워야 한다.
하위 클래스가 reset을 다시 정의하면 맨 앞에서 super().reset(env, rng)를 부른다.
무작위가 필요하면 self.rng(시나리오 시드로 만든 random.Random)만 쓴다.

특성 지표는 self.report("backtracks", 1)처럼 알려 준다. 이름과 모으는 방식은 REPORT_FIELDS에 정해져 있고,
알려 주지 않은 지표는 로그에 null로 남는다. 재계획 횟수(replans)는 needs_replan()이 자동으로 센다.
"""
REPLAN_MODES = ("never", "on_complaint", "every_step")

# 이름 -> (모으는 방식, 로그 필드, 뜻)
#   sum  = 판 안에서 더한다   max = 가장 큰 값   last = 마지막으로 알린 값
REPORT_FIELDS = {
    "mem_states":   ("max",  "compute_mem_states",   "동시에 저장한 최대 상태 수 (메모리)"),
    "h_violations": ("sum",  "compute_h_violations", "휴리스틱이 남은 비용을 실제보다 크게 잡은 횟수 (허용성, A*)"),
    "replans":      ("sum",  "compute_replans",      "계획을 다시 만든 횟수 (needs_replan이 자동으로 센다)"),
    "depth":        ("max",  "compute_depth",        "본 최대 깊이 (AND-OR, Expectimax)"),
    "backtracks":   ("sum",  "compute_backtracks",   "되돌아간 횟수 (CSP)"),
    "rules":        ("last", "compute_rules",        "지식베이스 규칙 개수 (논리 에이전트)"),
    "plan_len":     ("last", "compute_plan_len",     "계획이 만든 행동 수 (PDDL/HTN)"),
}


class Agent:
    name = "agent"

    def __init__(self, replan="never"):
        if replan not in REPLAN_MODES:
            raise ValueError(f"replan은 {REPLAN_MODES} 중 하나여야 한다")
        self.replan = replan
        self.env = None
        self.rng = None
        self.metrics = {}
        self._prev_slot = None

    def reset(self, env, rng):
        self.env = env
        self.rng = rng
        self.metrics = {}
        self._prev_slot = None

    def choose_action(self, obs):
        """obs(State)를 받아 행동(Action 또는 0~5)을 돌려준다. 하위 클래스가 구현한다."""
        raise NotImplementedError

    def report(self, name, value=1):
        """특성 지표 값을 알린다. 이름은 REPORT_FIELDS에 있는 것만 쓸 수 있다."""
        if name not in REPORT_FIELDS:
            raise KeyError(f"알 수 없는 지표 '{name}'. 쓸 수 있는 이름: {sorted(REPORT_FIELDS)}")
        mode = REPORT_FIELDS[name][0]
        old = self.metrics.get(name)
        if mode == "sum":
            self.metrics[name] = (old or 0) + value
        elif mode == "max":
            self.metrics[name] = value if old is None else max(old, value)
        else:
            self.metrics[name] = value

    def needs_replan(self, obs):
        """재계획 설정에 따라 지금 계획을 새로 세워야 하는지. 행동을 고를 때마다 한 번씩 호출한다.
        첫 호출은 항상 True(처음 계획)이고 재계획 횟수에 세지 않는다. 그 뒤의 True는 replans에 1씩 더한다.
        on_complaint는 새 항의가 나타난 단계에서 True."""
        first = self._prev_slot is None
        newly = obs.slot[0] == 1 and (self._prev_slot is None or self._prev_slot[0] != 1)
        self._prev_slot = obs.slot
        if first:
            self.metrics.setdefault("replans", 0)
            return True
        if self.replan == "every_step" or (self.replan == "on_complaint" and newly):
            self.report("replans", 1)
            return True
        return False
