from env import Agent, Action
from env.world import RESTAURANT_POS, DEST_POS, MOVES, MOVE_ACTIONS
from agents.horn_kb import KnowledgeBase, Rule
from agents.rule_agent import distances_to, step_toward

LOADED, WAITING = 1, 0

# 지각으로 매 단계 새로 TELL하는 술어. 이 이름의 사실은 단계마다 지우고 다시 말한다.
PERCEPT_PREDS = {"AtRest", "AtDest", "Waiting", "LoadedFor", "LoadedMenu", "Chase", "SlackD", "SlackL", "Learned", "Open"}


def build_rules(ban_rule=True, complaint_rules=True, policy="rule"):
    """KB의 규칙을 층으로 나눠 만든다. 규칙 하나가 하나의 지식 조각이다.

    policy="rule"    KB가 행동까지 정한다(싣기·배달·항의 쫓기·이동 목표).
    policy="random"  KB는 '해도 되는 행동'(Allowed)만 정하는 안전 필터이고, 그 중에서 무작위로 고른다. 항의 규칙은 쓰지 않는다.
    """
    s1 = [Rule("배달 가능", ("CanDeliver",), [("AtDest", "?d"), ("LoadedFor", "?d")])]
    if ban_rule:
        s1.append(Rule("3종 금지: 다른 두 메뉴를 싣고 있으면 이 식당은 막힘", ("Blocked", "?r"),
                       [("LoadedMenu", "?a"), ("LoadedMenu", "?b"), ("Distinct3", "?a", "?b", "?r")]))
    s1.append(Rule("학습으로 알게 된 막힘", ("Blocked", "?r"), [("Learned", "?r")]))
    if complaint_rules and policy == "rule":
        s1.append(Rule("쫓을 항의가 있다", ("ChaseAny",), [("Chase", "?c")]))
    if policy == "random":
        s2 = [Rule("싣기 가능", ("CanLoad",), [("AtRest", "?r"), ("Waiting", "?r"), ("not", ("Blocked", "?r"))])]
        s3 = [
            Rule("싣기가 가능하면 허용", ("Allowed", 4), [("CanLoad",)]),
            Rule("배달이 가능하면 허용", ("Allowed", 5), [("CanDeliver",)]),
            Rule("벽이 아닌 방향의 이동은 허용", ("Allowed", "?m"), [("Open", "?m")]),
        ]
        return [s1, s2, s3]
    s2 = [
        Rule("싣기 가능", ("CanLoad",), [("AtRest", "?r"), ("Waiting", "?r"), ("not", ("Blocked", "?r"))]),
        Rule("할 일: 적재한 주문의 배달지", ("TaskDest", "?d"), [("LoadedFor", "?d")]),
        Rule("할 일: 싣을 수 있는 식당", ("TaskRest", "?r"), [("Waiting", "?r"), ("not", ("Blocked", "?r"))]),
    ]
    s3 = []
    if complaint_rules:
        s3 += [
            Rule("항의 쫓는 중 배달할 여유가 있으면 배달", ("Act", "DELIVER"), [("Chase", "?c"), ("CanDeliver",), ("SlackD",)]),
            Rule("항의 쫓는 중 싣을 여유가 있으면 싣기", ("Act", "LOAD"), [("Chase", "?c"), ("CanLoad",), ("SlackL",)]),
        ]
    s3 += [
        Rule("항의가 없으면 배달 가능할 때 배달", ("Act", "DELIVER"), [("CanDeliver",), ("not", ("ChaseAny",))]),
        Rule("항의가 없으면 싣기 가능할 때 싣기", ("Act", "LOAD"), [("CanLoad",), ("not", ("ChaseAny",))]),
    ]
    s4 = [Rule("할 행동이 정해짐", ("ActAny",), [("Act", "?x")])]
    s5 = []
    if complaint_rules:
        s5.append(Rule("행동할 여유가 없으면 항의 배달지로 이동", ("GoChase", "?c"), [("Chase", "?c"), ("not", ("ActAny",))]))
    s5.append(Rule("항의도 행동도 없으면 가까운 할 일로 이동", ("GoTask",), [("not", ("ActAny",)), ("not", ("ChaseAny",))]))
    return [s1, s2, s3, s4, s5]


class LogicAgent(Agent):
    """논리 규칙 에이전트. 지각을 KB에 TELL하고, 전방 추론으로 얻은 사실을 ASK해서 행동을 고른다.

    KB-AGENT 틀(지각 TELL → 행동 ASK)을 그대로 따른다. KB가 정하는 것은 '무엇을 할지'(싣기·배달·항의 쫓기·이동 목표)이고,
    '어느 길로 갈지'는 지도를 보고 최단 경로를 잡는 내장 절차가 맡는다. 가장 가까운 할 일을 고르는 것도 내장 절차다.

    ban_rule=False     3종 금지 규칙을 KB에 넣지 않는다. 잘못된 싣기를 한 번 하면 그 상황(적재 메뉴 조합)과 식당을
                       '막힘'으로 학습해 KB에 규칙으로 더한다(규칙수가 늘어난다).
    complaint_rules=False  항의 관련 규칙을 넣지 않는다.
    policy="random"    KB를 안전 필터로만 쓴다. KB가 '해도 되는 행동'을 정하고 그 중에서 무작위로 고른다.
                       규칙을 모르는 정책(Random)에 지식을 얹으면 위반이 얼마나 줄어드는지 보려는 설정이다.
    """
    name = "logic"

    def __init__(self, replan="never", ban_rule=True, complaint_rules=True, policy="rule"):
        super().__init__(replan)
        if policy not in ("rule", "random"):
            raise ValueError("policy는 'rule' 또는 'random'이어야 한다")
        self.ban_rule = ban_rule
        self.complaint_rules = complaint_rules
        self.policy = policy

    def reset(self, env, rng):
        super().reset(env, rng)
        use_ban = self.ban_rule and env.preset.menu_ban
        self.kb = KnowledgeBase(build_rules(use_ban, self.complaint_rules, self.policy))
        n = len(RESTAURANT_POS)
        self.kb.tell(*[("Distinct3", a, b, r) for a in range(n) for b in range(n) for r in range(n)
                       if len({a, b, r}) == 3])
        self.learned = set()          # (식당, 그때 적재한 메뉴 집합)
        self._last = None             # (행동, 위치, 주문 상태, 식당, 적재 메뉴 집합)
        self.report("rules", self.kb.n_rules)

    # ---------- 지각 -> 사실 ----------
    def _menus_loaded(self, obs):
        return frozenset(cr for s, (cr, _, _) in zip(obs.status, self.env.rules.combos) if s == LOADED)

    def _tell_percept(self, obs):
        kb, combos = self.kb, self.env.rules.combos
        kb.retract_where(PERCEPT_PREDS | {"ActAny", "Act", "ChaseAny", "CanDeliver", "CanLoad", "Blocked",
                                          "TaskDest", "TaskRest", "GoChase", "GoTask", "Allowed"})
        p = self.env.preset
        facts = []
        if obs.pos in RESTAURANT_POS:
            facts.append(("AtRest", RESTAURANT_POS.index(obs.pos)))
        if obs.pos in DEST_POS:
            facts.append(("AtDest", DEST_POS.index(obs.pos)))
        for r in sorted({cr for s, (cr, _, _) in zip(obs.status, combos) if s == WAITING}):
            facts.append(("Waiting", r))
        for d in sorted({cd for s, (_, cd, _) in zip(obs.status, combos) if s == LOADED}):
            facts.append(("LoadedFor", d))
        menus = self._menus_loaded(obs)
        for m in sorted(menus):
            facts.append(("LoadedMenu", m))
        for a in MOVE_ACTIONS:
            if MOVES[obs.pos][a] is not None:
                facts.append(("Open", int(a)))
        for r, ms in self.learned:
            if ms == menus:
                facts.append(("Learned", r))
        if self.policy == "rule" and obs.slot[0] == 1:
            _, dest, left = obs.slot
            dist = distances_to(DEST_POS[dest])[obs.pos]
            if 0 < dist <= left:                       # 이미 늦었거나 이미 도착했으면 쫓지 않는다
                facts.append(("Chase", dest))
                if dist + p.deliver_time <= left:
                    facts.append(("SlackD",))
                if dist + p.load_time <= left:
                    facts.append(("SlackL",))
        kb.tell(*facts)

    def _learn_from_failure(self, obs):
        """직전에 싣기를 했는데 위치와 주문이 그대로면 그 싣기는 잘못된 행동이었다. 막힘으로 학습한다."""
        if self._last is None:
            return
        act, pos, status, r, menus = self._last
        if act == Action.LOAD and obs.pos == pos and obs.status == status:
            if (r, menus) not in self.learned:
                self.learned.add((r, menus))
                self.report("rules", self.kb.n_rules + len(self.learned))

    # ---------- 행동 고르기 ----------
    def choose_action(self, obs):
        self._learn_from_failure(obs)
        self._tell_percept(obs)
        self.kb.infer()
        action = self._ask(obs)
        r = RESTAURANT_POS.index(obs.pos) if obs.pos in RESTAURANT_POS else None
        self._last = (action, obs.pos, obs.status, r, self._menus_loaded(obs))
        return action

    def _ask(self, obs):
        kb = self.kb
        if self.policy == "random":
            allowed = sorted(e["?a"] for e in kb.query(("Allowed", "?a")))
            return Action(allowed[int(self.rng.random() * len(allowed))])
        if kb.holds(("Act", "DELIVER")):
            return Action.DELIVER
        if kb.holds(("Act", "LOAD")):
            return Action.LOAD
        for env_ in kb.query(("GoChase", "?c")):
            return step_toward(obs.pos, DEST_POS[env_["?c"]])
        if kb.holds(("GoTask",)):
            target = self._nearest_task(obs)
            if target is not None:
                return step_toward(obs.pos, target)
        return Action.DELIVER                      # 할 일이 없는데 안 끝난 경우는 없다

    def _nearest_task(self, obs):
        cands = [DEST_POS[e["?d"]] for e in sorted(self.kb.query(("TaskDest", "?d")), key=lambda e: e["?d"])]
        cands += [RESTAURANT_POS[e["?r"]] for e in sorted(self.kb.query(("TaskRest", "?r")), key=lambda e: e["?r"])]
        cands = [c for c in cands if c != obs.pos]
        if not cands:
            return None
        return min(cands, key=lambda c: distances_to(c)[obs.pos])
