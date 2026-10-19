from runner import run as run_mod
from runner import summarize as sm


def _make_logs(tmp_path):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-4", "--out", str(a)])
    run_mod.main(["--agent", "random", "--preset", "L2", "--seeds", "0-4", "--out", str(b)])   # 같은 시드 다시
    return a, b


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


def test_cli_prints_table_and_writes_csv(tmp_path, capsys):
    a, _ = _make_logs(tmp_path)
    out = tmp_path / "s.csv"
    sm.main([str(a), "--csv", str(out)])
    text = capsys.readouterr().out
    assert "| 알고리즘 |" in text and "random" in text
    assert out.read_text(encoding="utf-8").splitlines()[0].startswith("algorithm,preset")
