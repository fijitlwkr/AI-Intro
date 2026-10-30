"""작은 지식베이스(KB): 사실과 호른 규칙을 전방 추론으로 돌린다. 표준 라이브러리만 쓴다.

사실   = 튜플. 예: ("AtRest", 0), ("CanDeliver",)
변수   = '?'로 시작하는 문자열. 예: ("Waiting", "?r")
규칙   = Rule(head, body). body의 원소가 ("not", 원자)이면 부정(실패로서의 부정): 그 시점까지 모인 사실에 없으면 참.
층(strata) = 규칙 묶음의 리스트. 앞 층이 끝까지 추론된 뒤에 다음 층을 돌린다. 부정은 앞 층에서 만든 사실에만 걸 수 있다.
"""
from collections import namedtuple

Rule = namedtuple("Rule", "name head body")


def _is_var(x):
    return isinstance(x, str) and x.startswith("?")


def _match(atom, fact, env):
    if len(atom) != len(fact):
        return None
    env = dict(env)
    for a, f in zip(atom, fact):
        if _is_var(a):
            if a in env and env[a] != f:
                return None
            env[a] = f
        elif a != f:
            return None
    return env


def _subst(atom, env):
    return tuple(env.get(a, a) if _is_var(a) else a for a in atom)


class KnowledgeBase:
    def __init__(self, strata):
        self.strata = [list(s) for s in strata]
        self.facts = set()

    @property
    def n_rules(self):
        return sum(len(s) for s in self.strata)

    def tell(self, *facts):
        self.facts.update(facts)

    def retract_where(self, predicate_names):
        """지정한 술어 이름의 사실을 모두 지운다(매 단계 지각을 새로 말하기 전에 쓴다)."""
        self.facts = {f for f in self.facts if f[0] not in predicate_names}

    def holds(self, atom):
        return any(_match(atom, f, {}) is not None for f in self.facts)

    def query(self, atom):
        """atom과 맞는 사실마다 변수 대입을 돌려준다."""
        out = []
        for f in self.facts:
            env = _match(atom, f, {})
            if env is not None:
                out.append(env)
        return out

    def infer(self):
        """모든 층을 끝까지 전방 추론한다. 새로 만든 사실의 수를 돌려준다."""
        added = 0
        for rules in self.strata:
            changed = True
            while changed:
                changed = False
                for rule in rules:
                    for env in self._solutions(rule.body, {}):
                        new = _subst(rule.head, env)
                        if new not in self.facts:
                            self.facts.add(new)
                            added += 1
                            changed = True
        return added

    def _solutions(self, body, env):
        if not body:
            yield env
            return
        first, rest = body[0], body[1:]
        if first[0] == "not":
            if not any(_match(_subst(first[1], env), f, {}) is not None for f in self.facts):
                yield from self._solutions(rest, env)
            return
        for f in list(self.facts):
            nxt = _match(first, f, env)
            if nxt is not None:
                yield from self._solutions(rest, nxt)
