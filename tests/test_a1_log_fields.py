"""검증 A1: 로그에 입력 해시와 실행 환경이 기록되고, 입력이 다르면 요약이 경고한다."""
import json
import platform

from agents import REGISTRY
from env.scenario import generate, load_for, scenario_path
from runner import summarize as sm
from runner.play import run_game, scenario_sha256


def test_log_has_hash_and_environment():
    sc = generate("L2", 0)
    row = run_game(REGISTRY["rule"](), sc)
    assert row["scenario_sha256"] == scenario_sha256(sc)
    assert len(row["scenario_sha256"]) == 64
    assert row["python_version"] == platform.python_version()
    assert row["platform"] == platform.platform()
    assert row["schema_version"] == 3


def test_hash_is_same_for_file_and_generated():
    file_sc, from_file = load_for("L2", 3)
    assert from_file and scenario_path("L2", 3).exists()
    assert scenario_sha256(file_sc) == scenario_sha256(generate("L2", 3))


def test_hash_differs_when_content_differs():
    assert scenario_sha256(generate("L2", 0)) != scenario_sha256(generate("L2", 1))


def test_summarize_warns_on_different_inputs_for_same_seed():
    r1 = run_game(REGISTRY["rule"](), generate("L2", 0), run_id="a")
    r2 = run_game(REGISTRY["greedy"](), generate("L2", 0), run_id="b")
    ok = sm.warnings_for(*(lambda rows: (rows, sm.summarize(rows), 1))(sm.dedupe([r1, r2])[0]))
    assert not any("시나리오 내용이 다른" in n for n in ok)
    r2 = dict(r2, scenario_sha256="0" * 64)
    rows = sm.dedupe([r1, r2])[0]
    notes = sm.warnings_for(rows, sm.summarize(rows), 1)
    assert any("시나리오 내용이 다른" in n and "L2-000" in n for n in notes)


def test_old_logs_without_hash_do_not_warn():
    r1 = run_game(REGISTRY["rule"](), generate("L2", 0), run_id="a")
    old = {k: v for k, v in r1.items() if k != "scenario_sha256"}
    old["run_id"] = "b"; old["algorithm"] = "x"
    rows = sm.dedupe([r1, old])[0]
    assert not any("시나리오 내용이 다른" in n for n in sm.warnings_for(rows, sm.summarize(rows), 2))
