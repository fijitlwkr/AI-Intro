from env.agent import Agent
from env.world import Action, RESTAURANT_POS, DEST_POS
from agents.rule_agent import step_toward


class CSPAgent(Agent):
    name = "csp"

    def __init__(self, replan="never", fc=True):
        super().__init__(replan=replan)
        self.fc = fc
        self.plan = []

    def reset(self, env, rng):
        super().reset(env, rng)
        self.plan = []
        self.report("backtracks", 0)

    def choose_action(self, obs):
    
       # 계획이 없을 때만 CSP로 방문 순서 계산
        if not self.plan:
            variables, domains = self.make_variables(obs)
            solution = self.backtrack({}, variables, domains)

            if solution is not None:
                self.plan = sorted(solution, key=solution.get)


        # CSP 방문 순서에서 첫 번째 목적지 찾기
                        # 이미 완료된 작업은 계획에서 제거
        while self.plan:
            task = self.plan[0]
            index = int(task[1:])
            status = obs.status[index]

            if task.startswith("P") and status != 0:
                self.plan.pop(0)
            elif task.startswith("D") and status == 2:
                self.plan.pop(0)
            else:
                break
        if self.plan:
            task = self.plan[0]
            index = int(task[1:])
            restaurant, destination, count = self.env.rules.combos[index]

            if task.startswith("P"):
                target = RESTAURANT_POS[restaurant]
            else:
                target = DEST_POS[destination]
        # 목적지에 도착했다면 픽업 또는 배달
            if obs.pos == target:
                if task.startswith("P"):
                    return Action.LOAD
                else:
                    return Action.DELIVER

            # 아직 도착하지 않았다면 목적지로 이동
            return step_toward(obs.pos, target)
        return Action.UP

    def make_variables(self, obs):
        variables = []

        for i, status in enumerate(obs.status):
            if status == 0:  # 아직 픽업하지 않은 주문
                variables.append(f"P{i}")
                variables.append(f"D{i}")

            elif status == 1:  # 픽업했고 배달만 남은 주문
                variables.append(f"D{i}")

        domains = {
            var: list(range(1, len(variables) + 1))
            for var in variables
        }

        return variables, domains


    def check_precedence(self, assignment):
        for var, order in assignment.items():
            if var.startswith("P"):
                delivery = "D" + var[1:]

                if delivery in assignment:
                    if order >= assignment[delivery]:
                        return False

        return True

    def check_unique(self, assignment):
        orders = list(assignment.values())
        return len(orders) == len(set(orders))

    def check_menu_ban(self, assignment):
        if not self.env.preset.menu_ban:
            return True

        combos = self.env.rules.combos
        events = []

        for var, order in assignment.items():
            index = int(var[1:])
            restaurant = combos[index][0]
            events.append((order, var[0], index, restaurant))

        events.sort()

        loaded = set()

        for _, kind, index, restaurant in events:
            if kind == "P":
                loaded.add(index)

            elif kind == "D":
                loaded.discard(index)

            menus = {combos[i][0] for i in loaded}

            if len(menus) == 3:
                return False

        return True


    def is_consistent(self, assignment):
        return (
            self.check_unique(assignment)
            and self.check_precedence(assignment)
            and self.check_menu_ban(assignment)
        )

    def backtrack(self, assignment, variables, domains):
        # 모든 변수에 순서를 배정했다면 완료
        if len(assignment) == len(variables):
            return assignment.copy()

        # 아직 순서가 정해지지 않은 변수 선택
        unassigned = [v for v in variables if v not in assignment]
        var = min(unassigned, key=lambda v: len(domains[v]))

        # 가능한 방문 순서를 하나씩 시도
        for value in domains[var]:
            assignment[var] = value

            if self.is_consistent(assignment):
                    if self.fc:
                        next_domains = self.forward_check(
                            assignment, variables, domains
                        )
                    else:
                        next_domains = domains

                    if next_domains is not None:
                        result = self.backtrack(
                            assignment, variables, next_domains
                        )

                        if result is not None:
                            return result

            # 실패하면 이전 단계로 돌아가기
            del assignment[var]
            self.report("backtracks", 1)

        return None

    def forward_check(self, assignment, variables, domains):
        new_domains = {
            var: values.copy()
            for var, values in domains.items()
        }

        for var in variables:
            if var in assignment:
                continue

            valid_values = []

            for value in new_domains[var]:
                trial = assignment.copy()
                trial[var] = value

                if self.is_consistent(trial):
                    valid_values.append(value)

            if not valid_values:
                return None

            new_domains[var] = valid_values

        return new_domains