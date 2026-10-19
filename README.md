# AI-Intro

2026 가을 인공지능입문 팀 프로젝트. 배달 게임(Taxi 변형)에서 AI 알고리즘을 비교하는 실험 환경이다.

이 저장소에는 **코드만** 둔다. 게임 규칙, 용어, 비교표, 실험 기록은 Notion 허브에 있다.

## 준비

Python 3.13

```
pip install -r requirements.txt
python -m pytest -q          # 테스트 전부 통과해야 한다
```

## 폴더

| 폴더 | 내용 |
|---|---|
| `env/` | 환경. 지도, 규칙, 항의, 비용 계산, 노드 수 집계. 표준 라이브러리만 쓴다 |
| `agents/` | 알고리즘. 사람마다 파일 하나. `agents/__init__.py`의 `REGISTRY`에 한 줄 등록 |
| `runner/` | 한 판 실행(60초 제한), 로그 기록, 시나리오 생성 |
| `scenarios/` | 시나리오 파일(JSON). 모두가 같은 판을 쓰기 위한 입력 |
| `tests/` | 손계산 테스트 6개 등 |
| `logs/` | 실행 로그(JSONL). 저장소에 올라가지 않는다 |

## 실행

```
python -m runner.run --agent random --preset L2 --seeds 0-19
python -m runner.run --agent random --preset L2 --seeds 0-19 --replan on_complaint
```

로그는 `logs/`에 한 판당 한 줄로 쌓인다. `score_*`는 환경이 계산한 성과, `compute_*`는 알고리즘이 쓴 노력이다.
해당 없는 값은 `null`이다.

## 새 알고리즘 만들기

1. `agents/my_algo.py`에서 `env.Agent`를 상속하고 `choose_action(obs)`를 구현한다.
2. `agents/__init__.py`의 `REGISTRY`에 이름을 등록한다.
3. 실행: `python -m runner.run --agent my_algo --preset L0 --seeds 0-4`

```python
from env import Agent

class MyAgent(Agent):
    name = "my_algo"

    def choose_action(self, obs):
        # obs = State(pos, status, slot). 판이 시작될 때 reset()에서 지난 판의 계획을 비운다.
        # 탐색용: self.env.legal_actions(obs), self.env.successors(obs)  (노드 수가 자동으로 센다)
        # 무작위는 self.rng 만 쓴다.
        ...
```

- 행동은 6개: `UP DOWN LEFT RIGHT LOAD DELIVER` (`env.Action`). 6개 모두 낼 수 있고, 잘못된 행동은 시간 1, 비용 +10이다.
- `legal_actions(obs)`는 효과가 있는 행동만 돌려준다 (벽에 부딪히는 이동과 잘못된 행동은 뺀다).
- 재계획 시점은 `--replan` 설정(`never`, `on_complaint`, `every_step`)이고 `self.needs_replan(obs)`로 확인한다.
- 알고리즘은 현재 항의만 본다. 앞으로 올 항의는 보이지 않는다. 확률이 필요하면 `self.env.outcomes(state, action)`를 쓴다.

## 시나리오 파일

항의 목록이 `q`와 `T`로 만들어지므로 설정값(`env/presets.py`)이 바뀌면 다시 만든다.

```
python -m runner.make_scenarios                      # 모든 프리셋, 시드 0-19
python -m runner.make_scenarios --presets L2 --seeds 0-99
```

파일이 오래되면 `python -m pytest`가 알려 준다.
