import json

from agents import REGISTRY
from env.scenario import generate
from runner.play import run_game
from verify import a2_intake as it


def games(alg, seeds, commit="aaa", **kw):
    return [run_game(REGISTRY[alg](**kw), generate("L2", s), run_id=f"{alg}-{s}-{commit}", git_commit=commit) for s in seeds]


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def run(tmp_path, seeds="0-4"):
    files, rows, bad = it.read_all([tmp_path])
    return it.inspect(rows, "L2", it.parse_seeds(seeds)), bad


def test_clean_logs_in_nested_folder_have_no_issues(tmp_path):
    write(tmp_path / "x" / "y" / "a.jsonl", games("rule", range(5)))
    infos, bad = run(tmp_path)
    assert bad == [] and infos[0]["rows"] == 5 and infos[0]["issues"] == []


def test_missing_seeds_are_reported(tmp_path):
    write(tmp_path / "a.jsonl", games("rule", [0, 1, 4]))
    infos, _ = run(tmp_path)
    assert infos[0]["missing"] == [2, 3] and any("없음" in s for s in infos[0]["issues"])


def test_conflicting_duplicates_are_issue_but_identical_duplicates_are_not(tmp_path):
    same = games("rule", range(3))
    write(tmp_path / "a.jsonl", same + same)
    infos, _ = run(tmp_path, "0-2")
    assert infos[0]["issues"] == []
    changed = [dict(r) for r in same]
    changed[0]["score_cost"] += 5
    write(tmp_path / "b.jsonl", changed)
    infos, _ = run(tmp_path, "0-2")
    assert any("결과가 다른 중복" in s for s in infos[0]["issues"])


def test_mixed_and_dirty_commits_are_flagged(tmp_path):
    write(tmp_path / "a.jsonl", games("rule", range(3), commit="aaa") + games("rule", range(3, 5), commit="bbb+dirty"))
    infos, _ = run(tmp_path)
    text = " ".join(infos[0]["issues"])
    assert "커밋이 섞임" in text and "+dirty" in text


def test_unreadable_line_is_counted_and_main_writes_report(tmp_path, capsys):
    f = tmp_path / "a.jsonl"
    f.write_text(json.dumps(games("rule", [0])[0]) + "\n{깨진 줄\n", encoding="utf-8")
    out = tmp_path / "r.md"
    assert it.main([str(tmp_path), "--seeds", "0-0", "--out", str(out)]) == 0
    assert "읽지 못한 줄 1개" in out.read_text(encoding="utf-8")
    assert it.main([str(tmp_path / "empty")]) == 2
