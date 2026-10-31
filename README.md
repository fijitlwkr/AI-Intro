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
해당 없는 값은 `null`이다. 알고리즘 설정은 `--param 키=값`으로 넘기고(여러 번 가능) 로그의 `params`에 남는다.

```
python -m runner.run --agent random --preset L2 --seeds 0-19 --param legal_only=true
```

## 결과 요약

```
python -m runner.summarize                   # 공통 지표 표 + 특성지표 표
python -m runner.summarize --notion          # Notion 비교표 열 순서로 (값 붙여넣기용)
python -m runner.summarize --csv summary.csv
python -m runner.summarize --vs astar ucs --field compute_nodes_expanded   # 절감률: 같은 시드끼리 짝지어 비교
python -m runner.summarize --vs "csp:forward_checking=true" "csp:forward_checking=false" --field compute_backtracks   # 전파효과
```

- 같은 시드를 여러 번 돌렸으면 마지막 실행만 쓴다.
- 프리셋 값이 다르게 돌린 로그, 시드가 다른 알고리즘, 코드 버전이 섞인 경우는 `주의:`로 알려 준다.
- 최적격차는 L0·L1에서 `ucs` 로그(성공한 판)와 같은 시드끼리 계산한다. 그러려면 UCS도 같은 시드로 돌려야 한다.
- 항의초과율은 초과 건수 / 발생 건수다. 끝내지 못한 주문의 완료 시각은 H(500)로 계산한다.

## 로그 필드

| 필드 | 내용 |
|---|---|
| `schema_version`, `run_id`, `algorithm`, `replan`, `params`, `preset`, `preset_params`, `seed`, `scenario_id`, `git_commit` | 어떤 조건으로 돌렸는지. `git_commit`의 `+dirty`는 커밋하지 않은 변경이 있었다는 뜻 |
| `score_cost`, `score_avg_time`, `score_success`, `score_complaint_miss`, `score_total_time`, `score_wrong_actions`, `score_complaints`, `score_expired` | 환경이 계산한 성과 |
| `compute_sec`, `compute_nodes_expanded`, `compute_nodes_generated` | 행동 고르기에 쓴 시간, 노드 수(자동 집계, 탐색용 함수를 쓰지 않으면 null) |
| `compute_mem_states`, `compute_h_violations`, `compute_replans`, `compute_depth`, `compute_backtracks`, `compute_rules`, `compute_plan_len` | 알고리즘이 `self.report()`로 알린 특성 지표. 알리지 않으면 null |
| `failure`, `actions` | 실패 이유(`horizon`, `timeout`), 행동 목록 전체 |

## 들어 있는 알고리즘

| 이름 | 파일 | 설명 |
|---|---|---|
| `random` | `agents/random_agent.py` | 하한 기준선. 6개 행동 중 균등 선택. `legal_only=true`면 가능한 행동만 |
| `rule` | `agents/rule_agent.py` | 단순규칙기반. 탐색 없이 규칙 순서대로: 항의 배달지로 이동(마감 안에 갈 수 있을 때) → 내리기 → 싣기(3종 금지 회피) → 가장 가까운 할 일로 이동. `complaint_priority=false`면 항의를 무시 |
| `logic` | `agents/logic_agent.py` | 논리 규칙 에이전트. 지각을 KB에 TELL하고 호른 규칙을 전방 추론해 행동을 ASK한다(`agents/horn_kb.py`). 기본 KB는 `rule`과 같은 행동을 한다. `ban_rule=false`는 3종 금지 규칙을 빼고 실패에서 학습, `complaint_rules=false`는 항의 규칙을 뺀다. `policy=random`은 KB를 안전 필터로만 쓰고(해도 되는 행동을 KB가 정함) 그 중에서 무작위로 고른다. 규칙수는 `compute_rules`로 기록 |

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
- 재계획 시점은 `--replan` 설정(`never`, `on_complaint`, `every_step`)이고 `self.needs_replan(obs)`로 확인한다. 이 함수를 쓰면 재계획 횟수(`replans`)가 자동으로 센다.
- 특성 지표는 판 도중에 `self.report("backtracks", 1)`처럼 알린다. 쓸 수 있는 이름과 모으는 방식(합계, 최대, 마지막 값)은 `env/agent.py`의 `REPORT_FIELDS`에 있다. `reset`을 다시 정의하면 맨 앞에서 `super().reset(env, rng)`를 부른다.
- 알고리즘 설정(휴리스틱 종류 등)은 생성자 인자로 받으면 `--param`으로 바꿔 돌릴 수 있고 로그에 남는다.
- 알고리즘은 현재 항의만 본다. 앞으로 올 항의는 보이지 않는다. 확률이 필요하면 `self.env.outcomes(state, action)`를 쓴다.

## 시나리오 파일

항의 목록이 `q`와 `T`로 만들어지므로 설정값(`env/presets.py`)이 바뀌면 다시 만든다.

```
python -m runner.make_scenarios                      # 모든 프리셋, 시드 0-19
python -m runner.make_scenarios --presets L2 --seeds 0-99
```

파일이 오래되면 `python -m pytest`가 알려 준다.
