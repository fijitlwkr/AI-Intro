import json

import pytest

from agents import RandomAgent
from env import Agent, Action, generate
from runner import run as run_mod
from runner import summarize as sm
from runner.play import run_game


def _make_logs(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-4", "--out", str(a)])
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-4", "--out", str(b)])   # 같은 시드 다시
    return a, b


def _write(path, lines):
    path.write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lines), encoding="utf-8")


def test_duplicate_seeds_are_not_double_counted(tmp_path):
    a, b = _make_logs(tmp_path)
    rows, dropped = sm.dedupe(sm.load_rows([a, b]))
    assert len(rows) == 5 and dropped == 5
    (s,) = sm.summarize(rows)
    assert s["games"] == 5 and s["algorithm"] == "random" and s["preset"] == "L2"


def test_summary_values_match_manual_calculation(tmp_path):
    a, _ = _make_logs(tmp_path)
    rows = sm.load_rows([a])
    (s,) = sm.summarize(rows)
    costs = [r["score_cost"] for r in rows]
    assert s["cost_mean"] == sum(costs) / len(costs)
    assert s["cost_min"] == min(costs) and s["cost_max"] == max(costs)
    assert s["success_rate"] == sum(r["score_success"] for r in rows) / len(rows)
    # 항의초과율 = 전체 초과 건수 / 전체 발생 건수
    assert s["miss_pooled"] == sum(r["score_expired"] for r in rows) / sum(r["score_complaints"] for r in rows)
    # 위반율 = 전체 잘못된 행동 / 전체 행동
    assert s["wrong_rate"] == sum(r["score_wrong_actions"] for r in rows) / sum(len(r["actions"]) for r in rows)


def test_worst10_averages_worst_tenth():
    assert sm.worst10(list(range(1, 11))) == 10            # 10판 -> 1판
    assert sm.worst10(list(range(1, 21))) == 19.5          # 20판 -> 2판 (20, 19)
    assert sm.worst10([5]) == 5                            # 최소 1판


def test_variants_with_different_params_are_separate_rows(tmp_path):
    out = tmp_path / "v.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-2", "--out", str(out)])
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-2", "--param", "legal_only=true", "--out", str(out)])
    rows, dropped = sm.dedupe(sm.load_rows([out]))
    assert dropped == 0
    labels = [s["label"] for s in sm.summarize(rows)]
    assert labels == ["random", "random (legal_only=True)"]


def test_notion_table_format(tmp_path):
    a, _ = _make_logs(tmp_path)
    rows, _ = sm.dedupe(sm.load_rows([a]))
    head, (row,) = sm.notion_table(sm.summarize(rows))
    assert head == ["알고리즘", "총비용", "평균배달시간", "성공률", "항의초과율", "계산시간(초)", "측정조건"]
    assert row[0] == "random" and row[3].endswith("%") and row[4].endswith("%")
    assert row[6].startswith("시드 5, 20") and "L2" not in row[6]         # 기본 설정(L2)은 적지 않는다


def test_notion_leaves_not_applicable_blank_and_marks_other_presets(tmp_path):
    out = tmp_path / "l0.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L0", "--seeds", "0-2", "--out", str(out)])
    rows, _ = sm.dedupe(sm.load_rows([out]))
    _, (row,) = sm.notion_table(sm.summarize(rows))
    assert row[4] == ""                    # 항의가 없는 설정: 0이 아니라 비움
    assert row[6].endswith("L0")


class Fixed(Agent):
    """정해진 비용을 만드는 시험용 에이전트: 벽에 부딪히며 시간을 보내다 끝난다."""
    name = "fixed_test"

    def choose_action(self, obs):
        self.report("backtracks", 1)
        return Action.UP if obs.pos[0] > 0 else Action.LEFT


def test_optimal_gap_uses_reference_on_same_seeds(tmp_path):
    rows = []
    for seed in range(3):
        a = run_game(RandomAgent(), generate("L0", seed), run_id=f"20261019-000000-random-{seed}")
        rows.append(a)
        b = dict(a); b.update(algorithm="ucs", score_cost=100, score_success=True, params={})
        rows.append(b)
        c = dict(a); c.update(algorithm="greedy", score_cost=150, score_success=True)
        rows.append(c)
    summary = sm.summarize(rows)
    assert sm.add_optimal_gap(summary, rows, "ucs") is True
    gap = {s["algorithm"]: s["opt_gap"] for s in summary}
    assert gap["ucs"] == 0 and gap["greedy"] == pytest.approx(0.5)
    assert gap["random"] is not None and gap["random"] > 0


def _run(tmp_path, agent, preset, seeds):
    out = tmp_path / f"{agent.name}_{preset}.jsonl"
    with out.open("a", encoding="utf-8") as f:
        for s in seeds:
            f.write(json.dumps(run_game(agent, generate(preset, s), run_id=f"20261019-0-{s}"), ensure_ascii=False) + "\n")
    return out


def test_optimal_gap_is_blank_for_presets_with_complaints():
    rows = [run_game(RandomAgent(), generate("L2", 0), run_id="20261019-1")]
    ucs = dict(rows[0]); ucs.update(algorithm="ucs", score_success=True, params={})
    summary = sm.summarize(rows + [ucs])
    sm.add_optimal_gap(summary, rows + [ucs], "ucs")
    assert all(s["opt_gap"] is None for s in summary)


def test_vs_report_pairs_by_preset_and_seed():
    base = run_game(RandomAgent(), generate("L1", 0), run_id="20261019-1")
    a = dict(base); a.update(algorithm="astar", compute_nodes_expanded=300)
    b = dict(base); b.update(algorithm="ucs", compute_nodes_expanded=1000)
    text = sm.vs_report([a, b], "astar", "ucs", "compute_nodes_expanded")
    assert "70.0% 줄임" in text and "짝지은 판 1" in text
    # 설정으로 변형 지정
    c = dict(base); c.update(algorithm="csp", params={"fc": True}, compute_backtracks=10)
    d = dict(base); d.update(algorithm="csp", params={"fc": False}, compute_backtracks=40)
    assert "75.0% 줄임" in sm.vs_report([c, d], "csp:fc=true", "csp:fc=false", "compute_backtracks")
    assert "계산할 수 없습니다" in sm.vs_report([a], "astar", "ucs", "compute_nodes_expanded")


def test_different_preset_values_are_not_merged_and_warn():
    r1 = run_game(RandomAgent(), generate("L2", 0), run_id="20261019-1")
    r2 = run_game(RandomAgent(), generate("L2", 1), run_id="20261019-2")
    r2["preset_params"] = dict(r2["preset_params"], T=15)                  # [초안] 값이 바뀐 뒤의 로그
    rows, _ = sm.dedupe([r1, r2])
    summary = sm.summarize(rows)
    assert len(summary) == 2                                               # 합쳐서 평균 내지 않는다
    notes = sm.warnings_for(rows, summary, 1)
    assert any("프리셋 값이 다른" in n for n in notes)


def test_warns_when_seed_sets_or_commits_differ():
    r1 = run_game(RandomAgent(), generate("L2", 0), run_id="20261019-1", git_commit="aaa111")
    r2 = run_game(RandomAgent(), generate("L2", 1), run_id="20261019-2", git_commit="bbb222")
    b1 = dict(r1); b1.update(algorithm="other")
    rows, _ = sm.dedupe([r1, r2, b1])
    notes = sm.warnings_for(rows, sm.summarize(rows), 1)
    assert any("시드가 다릅니다" in n for n in notes)
    assert any("코드 버전" in n for n in notes)


def test_trait_table_shows_reported_columns_only(tmp_path):
    class Rep(Agent):
        name = "rep_test"
        def choose_action(self, obs):
            self.report("backtracks", 1)
            return self.env.legal_actions(obs)[0]
    out = _run(tmp_path, Rep(), "L1", range(2))
    rows, _ = sm.dedupe(sm.load_rows([out]))
    head, body = sm.trait_table(sm.summarize(rows))
    assert "백트랙수" in head and "메모리" not in head
    assert sm.trait_table(sm.summarize(sm.dedupe([run_game(RandomAgent(), generate("L1", 0))])[0]))[0].count("노드수") == 0


def test_cli_tables_notion_and_csv(tmp_path, capsys):
    a, _ = _make_logs(tmp_path)
    out = tmp_path / "s.csv"
    sm.main([str(a), "--csv", str(out)])
    text = capsys.readouterr().out
    assert "## 공통 지표" in text and "random" in text
    assert out.read_text(encoding="utf-8").splitlines()[0].startswith("알고리즘,프리셋")
    sm.main([str(a), "--notion", "--csv", str(out)])
    assert "| 측정조건 |" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8").splitlines()[0].startswith("알고리즘,총비용")
