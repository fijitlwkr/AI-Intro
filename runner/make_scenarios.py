"""시나리오 파일(scenarios/*.json)을 만든다. 프리셋 설정값이 바뀌면 다시 실행해서 덮어쓴다.

예)  python -m runner.make_scenarios                       # 전체 프리셋, 시드 0-19
     python -m runner.make_scenarios --presets L2 --seeds 0-99
"""
import argparse

from env import PRESETS, scenario as scenario_mod
from .run import parse_seeds


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--presets", nargs="+", default=sorted(PRESETS), choices=sorted(PRESETS))
    ap.add_argument("--seeds", default="0-19")
    args = ap.parse_args(argv)
    count = 0
    for name in args.presets:
        for seed in parse_seeds(args.seeds):
            scenario_mod.save(scenario_mod.generate(PRESETS[name], seed))
            count += 1
    print(f"시나리오 {count}개를 scenarios/ 에 저장했습니다.")


if __name__ == "__main__":
    main()
