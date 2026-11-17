"""CSP 수정 제안. 원본 feature/csp는 변경하지 않는다.

기준: d9fb2898a8c8c786bf1e32bb8a3c7e9aca8cb73e / agents/csp_agent.py
원본의 변수·MRV·FC·백트래킹을 유지하고 부분 적재/일괄 처리/계획 실행을 보완한다.
최적 비용을 탐색하는 에이전트라는 주장은 하지 않는다.
"""
from env.world import Action, RESTAURANT_POS, DEST_POS
from agents.rule_agent import step_toward
from .fixtures.csp_d9fb289 import CSPAgent


class CSPPlanError(RuntimeError):
    """해가 없거나 실행 불가능한 계획. 임의 행동으로 실패를 숨기지 않는다."""


class CSPCandidateAgent(CSPAgent):
    name = "csp_candidate"

    def reset(self, env, rng):
        super().reset(env, rng)
        self._planning_status = tuple(env.state.status)
        self._planned = False

    def make_variables(self, obs):
        self._planning_status = tuple(obs.status)
        variables, domains = super().make_variables(obs)
        # FC에서 부분 순서를 성급히 금지하지 않으면 빈 순서 슬롯이 많아진다.
        # 이미 실은 주문을 먼저 내리고, 식당별 P 묶음 -> D 묶음인 실행 가능한
        # 기본 순서의 값을 먼저 시도한다. MRV/FC/백트래킹 자체는 원본을 유지한다.
        preferred = [f"D{i}" for i, status in enumerate(obs.status) if status == 1]
        combos = self.env.rules.combos
        for restaurant in sorted({r for (r, _, _), status in zip(combos, obs.status) if status == 0}):
            indices = [i for i, ((r, _, _), status) in enumerate(zip(combos, obs.status))
                       if r == restaurant and status == 0]
            preferred.extend(f"P{i}" for i in indices)
            preferred.extend(f"D{i}" for i in indices)
        ranks = {task: rank for rank, task in enumerate(preferred, 1)}
        for task in domains:
            domains[task].sort(key=lambda rank: (rank != ranks[task], rank))
        return variables, domains

    def _build_plan(self, obs):
        self.env._check_deadline()
        variables, domains = self.make_variables(obs)
        solution = self.backtrack({}, variables, domains)
        if solution is None:
            raise CSPPlanError("CSP 방문 순서 해가 없습니다.")
        self.plan = sorted(solution, key=solution.get)
        self._planned = True

    def choose_action(self, obs):
        self.env._check_deadline()
        if self.needs_replan(obs) or not self._planned:
            self._build_plan(obs)
        while self.plan:
            task = self.plan[0]
            index = int(task[1:])
            if (task.startswith("P") and obs.status[index] != 0) or (
                    task.startswith("D") and obs.status[index] == 2):
                self.plan.pop(0)
            else:
                break
        if not self.plan:
            raise CSPPlanError("실행할 작업이 없는 CSP 계획입니다.")
        task = self.plan[0]
        restaurant, destination, _ = self.env.rules.combos[int(task[1:])]
        pickup = task.startswith("P")
        target = RESTAURANT_POS[restaurant] if pickup else DEST_POS[destination]
        if obs.pos == target:
            action = Action.LOAD if pickup else Action.DELIVER
        else:
            action = step_toward(obs.pos, target)
        if action not in self.env.legal_actions(obs):
            raise CSPPlanError(f"계획이 부적법한 행동을 요구합니다: {task}, {action}")
        return action

    def backtrack(self, assignment, variables, domains):
        self.env._check_deadline()
        return super().backtrack(assignment, variables, domains)

    def is_consistent(self, assignment):
        self.env._check_deadline()
        return super().is_consistent(assignment)

    def check_menu_ban(self, assignment):
        self.env._check_deadline()
        combos = self.env.rules.combos
        status = list(self._planning_status)
        events = {rank: task for task, rank in assignment.items()}
        # 미배정 위치 앞까지의 확정된 연속 접두부만 검사한다.
        # 빈 위치에 배달이 들어갈 수 있는데 먼저 금지하면 FC가 정상 해도 제거한다.
        for rank in range(1, len(assignment) + 1):
            if rank not in events:
                break
            task = events[rank]
            index = int(task[1:])
            restaurant, destination, _ = combos[index]
            if task.startswith("P"):
                if status[index] != 0:
                    continue
                menus = {r for (r, _, _), s in zip(combos, status) if s == 1}
                if self.env.preset.menu_ban and len(menus | {restaurant}) >= 3:
                    return False
                # LOAD는 같은 식당의 대기 주문을 한꺼번에 싣는다.
                status = [1 if r == restaurant and s == 0 else s
                          for (r, _, _), s in zip(combos, status)]
            else:
                if status[index] == 2:
                    continue
                if status[index] != 1:
                    return False
                # DELIVER는 같은 배달지의 적재 주문을 한꺼번에 내린다.
                status = [2 if d == destination and s == 1 else s
                          for (_, d, _), s in zip(combos, status)]
        return True
