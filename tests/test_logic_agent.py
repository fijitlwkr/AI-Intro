from agents import REGISTRY
from agents.horn_kb import KnowledgeBase, Rule
from agents.logic_agent import LogicAgent, build_rules
from env import PRESETS, generate
from runner.play import run_game


def _game(cls, preset, seed, **kw):
    return run_game(cls(**kw), generate(PRESETS[preset], seed))


# ---------- KB 엔진 ----------
def test_forward_chaining_with_variables():
    kb = KnowledgeBase([[Rule("r", ("Path", "?a", "?c"), [("Edge", "?a", "?b"), ("Edge", "?b", "?c")])]])
    kb.tell(("Edge", 1, 2), ("Edge", 2, 3), ("Edge", 3, 4))
    kb.infer()
    assert kb.holds(("Path", 1, 3)) and kb.holds(("Path", 2, 4))
    assert not kb.holds(("Path", 1, 4))


def test_negation_uses_earlier_strata_only_after_they_finish():
    s1 = [Rule("a", ("Bad", "?x"), [("Item", "?x"), ("Flag", "?x")])]
    s2 = [Rule("b", ("Good", "?x"), [("Item", "?x"), ("not", ("Bad", "?x"))])]
    kb = KnowledgeBase([s1, s2])
    kb.tell(("Item", 1), ("Item", 2), ("Flag", 2))
    kb.infer()
    assert kb.holds(("Good", 1)) and not kb.holds(("Good", 2))


def test_retract_where_removes_only_named_predicates():
    kb = KnowledgeBase([[]])
    kb.tell(("A", 1), ("B", 2))
    kb.retract_where({"A"})
    assert not kb.holds(("A", 1)) and kb.holds(("B", 2))


# ---------- 에이전트 ----------
def test_registered_and_rule_count():
    assert REGISTRY["logic"] is LogicAgent
    full = sum(len(s) for s in build_rules(True, True))
    assert sum(len(s) for s in build_rules(False, True)) == full - 1
    assert sum(len(s) for s in build_rules(True, False)) < full - 1


def test_full_kb_plays_exactly_like_rule_agent():
    # 같은 규칙을 호른 규칙으로 옮긴 것이므로 모든 프리셋에서 행동 열이 같아야 한다.
    for preset in ("L0", "L1", "L2", "L3"):
        for seed in range(6):
            a = _game(REGISTRY["rule"], preset, seed)
            b = _game(LogicAgent, preset, seed)
            assert a["actions"] == b["actions"], (preset, seed)


def test_full_kb_never_violates_and_reports_rules():
    for preset in ("L1", "L2", "L3"):
        line = _game(LogicAgent, preset, 3)
        assert line["score_success"] is True
        assert line["score_wrong_actions"] == 0
        assert line["compute_rules"] == sum(len(s) for s in build_rules(True, True))
        assert line["compute_nodes_expanded"] is None


def test_without_ban_rule_violates_then_learns_and_recovers():
    wrong, learned_games = 0, 0
    base = sum(len(s) for s in build_rules(False, True))
    for seed in range(30):
        line = _game(LogicAgent, "L1", seed, ban_rule=False)
        assert line["score_success"] is True               # 시행착오 뒤에도 끝낸다
        wrong += line["score_wrong_actions"]
        if line["score_wrong_actions"]:
            learned_games += 1
            assert line["compute_rules"] > base            # 실패한 상황이 규칙으로 늘었다
            assert line["score_wrong_actions"] <= line["compute_rules"] - base   # 같은 실수를 되풀이하지 않는다
    assert wrong > 0 and learned_games > 0


def test_ban_rule_flag_is_ignored_when_preset_has_no_ban():
    a = _game(LogicAgent, "L0", 2)
    b = _game(LogicAgent, "L0", 2, ban_rule=False)
    assert a["actions"] == b["actions"] and a["score_wrong_actions"] == 0


def test_without_complaint_rules_matches_rule_agent_without_priority():
    for seed in range(6):
        a = _game(REGISTRY["rule"], "L2", seed, complaint_priority=False)
        b = _game(LogicAgent, "L2", seed, complaint_rules=False)
        assert a["actions"] == b["actions"], seed
