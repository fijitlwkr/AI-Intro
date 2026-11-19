from pathlib import Path

import pytest

from env import PRESETS, generate
from env import scenario as sc_mod


def test_same_seed_same_scenario():
    assert generate("L2", 5) == generate("L2", 5)
    assert generate("L2", 5) != generate("L2", 6)


def test_all_menus_appear_when_ensured():
    for p in PRESETS.values():
        for seed in range(30):
            assert len({r for r, _ in generate(p, seed).orders}) == 3


def test_complaint_spacing_follows_deadline_rule():
    """다음 항의는 앞 항의의 마감(t0+T) 다음 시각부터 가능하다."""
    for name in ("L2", "L3"):
        p = PRESETS[name]
        for seed in range(40):
            cs = generate(p, seed).complaints
            assert all(0 <= t < p.horizon for t, _ in cs)
            for (t0, _), (t1, _) in zip(cs, cs[1:]):
                assert t1 >= t0 + p.T + 1


def test_no_complaints_when_q_is_zero():
    assert generate("L0", 3).complaints == () and generate("L1", 3).complaints == ()


def test_json_roundtrip(tmp_path):
    s = generate("L3", 11)
    path = sc_mod.save(s, tmp_path)
    assert sc_mod.load(path) == s


def test_committed_scenario_files_match_current_presets():
    """프리셋 값(q, T, n 등)이 바뀌었는데 scenarios/ 를 다시 만들지 않았으면 여기서 실패한다."""
    files = sorted(Path(sc_mod.SCENARIO_DIR).glob("*.json"))
    assert files, "scenarios/ 가 비어 있다. python -m runner.make_scenarios 를 실행하세요."
    for f in files:
        s = sc_mod.load(f)
        if s.preset.startswith("E"):     # 손으로 쓴 특화 시나리오는 생성기와 비교하지 않는다(아래 E1 테스트가 따로 검사)
            continue
        assert s == generate(s.preset, s.seed), f"{f.name}이(가) 현재 설정으로 만든 결과와 다르다. 다시 만드세요."


def test_stale_file_is_rejected(tmp_path):
    from dataclasses import replace
    s = generate("L2", 1)
    stale = replace(s, params=tuple((k, 0.5 if k == "q" else v) for k, v in s.params))
    with pytest.raises(ValueError):
        sc_mod.check_matches_preset(stale, "L2")


def test_make_scenarios_skips_hand_written_presets(tmp_path, monkeypatch):
    import runner.make_scenarios as ms
    saved = []
    monkeypatch.setattr(sc_mod, "save", lambda s, d=None: saved.append(s.preset))
    ms.main(["--seeds", "0-0"])
    assert saved and not any(p.startswith("E") for p in saved)
    with pytest.raises(SystemExit):
        ms.main(["--presets", "E1"])


def test_hand_written_preset_does_not_fall_back_to_generation():
    with pytest.raises(FileNotFoundError):
        sc_mod.load_for("E1", 1)


def test_e1_file_follows_structure_rules():
    from env.presets import PRESETS
    from env.world import RESTAURANT_NAMES
    s, from_file = sc_mod.load_for("E1", 0)
    assert from_file
    p = PRESETS["E1"]
    sc_mod.check_matches_preset(s, p)
    assert len(s.orders) == p.n and {r for r, _ in s.orders} == set(range(len(RESTAURANT_NAMES)))
    times = [t for t, _ in s.complaints]
    assert times == sorted(times) and all(b - a >= p.T + 1 for a, b in zip(times, times[1:]))
    assert all(0 <= t < p.horizon for t in times)
