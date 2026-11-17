"""검증 A1 ① 입력 동일성: scenarios/ 파일 전부가 생성기 출력과 같은지 확인한다.

python -m verify.a1_inputs [--dir scenarios] [--out 결과.json]
이름이 E로 시작하는 프리셋(손으로 쓴 특화 시나리오)은 생성기와 비교하지 않고 해시만 적는다.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from env import PRESETS
from env.scenario import SCENARIO_DIR, generate, load, check_matches_preset
from runner.play import scenario_sha256

NAME = re.compile(r"^(?P<preset>[A-Za-z0-9]+)_(?P<seed>\d{3,})\.json$")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=str(SCENARIO_DIR))
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    checked, hand_written, bad, skipped = 0, [], [], []
    hashes = {}
    for path in sorted(Path(args.dir).glob("*.json")):
        m = NAME.match(path.name)
        if not m:
            skipped.append(path.name)
            continue
        preset, seed = m["preset"], int(m["seed"])
        if preset not in PRESETS:
            skipped.append(path.name)
            continue
        sc = load(path)
        hashes[path.name] = scenario_sha256(sc)
        if preset.startswith("E"):
            hand_written.append(path.name)
            continue
        try:
            check_matches_preset(sc, preset)
            same = sc.to_json() == generate(PRESETS[preset], seed).to_json()
        except ValueError as e:
            bad.append((path.name, str(e)))
            continue
        checked += 1
        if not same:
            bad.append((path.name, "생성기 출력과 내용이 다름"))

    result = {"dir": args.dir, "compared_with_generator": checked, "hand_written_hash_only": len(hand_written),
              "skipped": skipped, "mismatches": bad, "hashes": hashes}
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"생성기와 비교한 파일 {checked}개, 불일치 {len(bad)}건, 손으로 쓴 파일(해시만) {len(hand_written)}개, 건너뜀 {len(skipped)}개")
    for name, why in bad[:20]:
        print("  불일치:", name, why)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
