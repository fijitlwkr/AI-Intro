"""검증 A2 작업 흐름: 교차 확인, 같은 커밋 일괄 실행, 순위 안정성 표시."""
import json

from agents import REGISTRY
from env.scenario import generate
from runner.play import run_game
from verify import a2_crosscheck as cc
from verify import a2_pairs as a2
from verify import run_registered as rr


def games(alg, seeds, commit="aaa", **kw):
    return [run_game(REGISTRY[alg](**kw), generate("L2", s), run_id=f"{alg}-{s}", git_commit=commit) for s in seeds]


def write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_crosscheck_identical_logs_match(tmp_path):
    ours, theirs = games("rule", range(5)), games("rule", range(5), commit="bbb")
    res = cc.crosscheck(ours, theirs)
    assert res[0]["identical"] == 5 and res[0]["differ"] == 0 and res[0]["commits"] == ["bbb"]


def test_crosscheck_detects_changed_score_and_actions():
    ours = games("rule", range(5))
    theirs = games("rule", range(5), commit="old")
    theirs[2] = dict(theirs[2], score_cost=theirs[2]["score_cost"] + 1)
    theirs[3] = dict(theirs[3], actions=theirs[3]["actions"][:-1])
    res = cc.crosscheck(ours, theirs)[0]
    assert res["differ"] == 2 and res["differ_seeds"] == [2, 3]
    assert res["differ_fields"]["score_cost"] == 1 and res["differ_fields"]["actions"] == 1


def test_crosscheck_lists_settings_we_do_not_have():
    ours = games("rule", range(3))
    theirs = games("greedy", range(3), commit="old")
    res = cc.crosscheck(ours, theirs)[0]
    assert res["matched"] == 0 and res["missing_ours"] == 3
    assert "우리에게 없는 설정" in cc.render([res], [1], [1])


def test_crosscheck_handles_logs_without_hash_or_new_fields():
    ours = games("rule", range(3))
    theirs = [{k: v for k, v in r.items() if k not in ("scenario_sha256", "python_version", "platform")} for r in games("rule", range(3))]
    assert cc.crosscheck(ours, theirs)[0]["identical"] == 3


def test_crosscheck_main_reads_folders(tmp_path, capsys):
    (tmp_path / "ours").mkdir(); (tmp_path / "theirs").mkdir()
    write(tmp_path / "ours" / "a.jsonl", games("rule", range(3)))
    write(tmp_path / "theirs" / "b.jsonl", games("rule", range(3), commit="zzz"))
    assert cc.main(["--ours", str(tmp_path / "ours"), "--theirs", str(tmp_path / "theirs")]) == 0
    assert "모든 짝이 일치한다" in capsys.readouterr().out


def test_crosscheck_reads_nested_folders(tmp_path, capsys):
    (tmp_path / "ours").mkdir()
    deep = tmp_path / "theirs" / "logs" / "astar_final"
    deep.mkdir(parents=True)
    write(tmp_path / "ours" / "a.jsonl", games("rule", range(3)))
    write(deep / "b.jsonl", games("rule", range(3), commit="zzz"))
    assert cc.main(["--ours", str(tmp_path / "ours"), "--theirs", str(tmp_path / "theirs")]) == 0
    assert "모든 짝이 일치한다" in capsys.readouterr().out


def test_run_registered_dry_run_lists_seven_configs(capsys):
    assert rr.main(["--out", "x", "--dry-run"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 7 and any("on_complaint" in l for l in lines) and all("--seeds 0-99" in l for l in lines)


def test_run_registered_refuses_dirty_tree(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "is_dirty", lambda: True)
    assert rr.main(["--out", str(tmp_path / "o")]) == 2
    assert not (tmp_path / "o").exists()


def test_run_registered_configs_match_registered_pairs():
    pairs = json.loads(a2.PAIRS_FILE.read_text(encoding="utf-8"))["pairs"]
    needed = {a2.parse_spec(p[k]) [0] + "@" + a2.parse_spec(p[k])[2] for p in pairs for k in ("a", "b")}
    have = {name.replace("_never", "@never").replace("_on_complaint", "@on_complaint") for name, _ in rr.CONFIGS}
    for spec in needed:
        base, replan = spec.split("@")
        assert any(h == spec or h == base for h in have), spec


def test_segment_sign_shown_only_for_significant_pairs():
    rows = []
    for s in range(100):
        base = 50 + s % 7
        rows += [dict(a2_row := {"algorithm": "a", "seed": s, "preset": "L2", "replan": "never", "params": {}, "score_cost": base + (0.4 if s < 50 else -0.4),
                  "score_avg_time": 40.0, "score_expired": 0, "score_complaints": 2, "score_success": True, "run_id": "r"}),
                 {"algorithm": "b", "seed": s, "preset": "L2", "replan": "never", "params": {}, "score_cost": base,
                  "score_avg_time": 40.0, "score_expired": 0, "score_complaints": 2, "score_success": True, "run_id": "r"}]
    r = a2.analyze_pair(rows, {"id": 1, "a": "a", "b": "b", "expect": {"score_cost": "tie"}, "text": ""}, "L2", 500)
    text = a2.render([r], {"rates": {}, "saturated": False}, [], "L2", 500, len(rows))
    assert "해당 없음(동률" in text and "**아니오**" not in text.split("순위 안정성")[1].split("시드 수 충분성")[0]


def test_v2_set_lists_bfs_andor_expectimax_commands():
    cmds = rr.commands("out", "L2", "100-199", rr.CONFIGS_V2)
    names = [n for _, n in cmds]
    assert names == ["astar_never", "astar_on_complaint", "ucs", "bfs", "andor", "expectimax"]
    assert all("100-199" in c for c, _ in cmds)


def test_v2_pairs_file_is_loadable_and_ids_do_not_overlap_v1():
    v1 = json.loads(a2.PAIRS_FILE.read_text(encoding="utf-8"))["pairs"]
    v2 = json.loads(a2.PAIRS_FILE.with_name("a2_registered_pairs_v2.json").read_text(encoding="utf-8"))["pairs"]
    assert not {p["id"] for p in v1} & {p["id"] for p in v2}
    assert {p["role"] for p in v2} <= {"judged", "exploratory"}


def test_e1_report_has_one_row_per_agent(tmp_path):
    from verify import a3_e1_report as rep
    sc = generate("L2", 0)
    rows = [dict(run_game(REGISTRY["rule"](), sc, run_id="x", git_commit="aaa"), preset="E1", seed=0)]
    write(tmp_path / "e1.jsonl", rows)
    text = rep.render(rep.read([tmp_path]))
    assert text.count("\n") == 2 and "rule@never" in text


def test_v3_set_and_pairs_file():
    cmds = rr.commands("out", "L3", "0-99", rr.SETS["v3"])
    assert [n for _, n in cmds] == ["astar_never", "ucs", "bfs", "andor", "expectimax", "idastar_memo"]
    assert "memo=true" in cmds[-1][0]
    v3 = json.loads(a2.PAIRS_FILE.with_name("a2_registered_pairs_v3.json").read_text(encoding="utf-8"))["pairs"]
    used = {p["id"] for f in ("a2_registered_pairs.json", "a2_registered_pairs_v2.json")
            for p in json.loads(a2.PAIRS_FILE.with_name(f).read_text(encoding="utf-8"))["pairs"]}
    assert not used & {p["id"] for p in v3}
