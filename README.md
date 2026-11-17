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
| `greedy` | `agents/greedy_agent.py` | Greedy Best-first. 전체 frontier에서 `h`만으로 선택하고 같은 값은 생성 순서. `heuristic=mst`(기본) 또는 `max_distance`, `objective=c1`(기본) 또는 `c2` |
| `astar` | `agents/astar_agent.py` | A*. `f=g+h`, 더 싼 경로 발견 시 재탐색. `heuristic=max_distance/mst/constraint`, `objective=c1/c2`. 기본은 mst, c1, 처음 한 번 계획 |
| `rule` | `agents/rule_agent.py` | 단순규칙기반. 탐색 없이 규칙 순서대로: 항의 배달지로 이동(마감 안에 갈 수 있을 때) → 내리기 → 싣기(3종 금지 회피) → 가장 가까운 할 일로 이동. `complaint_priority=false`면 항의를 무시 |
| `logic` | `agents/logic_agent.py` | 논리 규칙 에이전트. 지각을 KB에 TELL하고 호른 규칙을 전방 추론해 행동을 ASK한다(`agents/horn_kb.py`). 기본 KB는 `rule`과 같은 행동을 한다. `ban_rule=false`는 3종 금지 규칙을 빼고 실패에서 학습, `complaint_rules=false`는 항의 규칙을 뺀다. `policy=random`은 KB를 안전 필터로만 쓰고(해도 되는 행동을 KB가 정함) 그 중에서 무작위로 고른다. 규칙수는 `compute_rules`로 기록 |

## Greedy 실행과 결과 확인

```powershell
python -m runner.run --agent greedy --preset L2 --seeds 0-99 --param heuristic=mst --param objective=c1
python -m runner.summarize --preset L2
python -m runner.summarize --preset L2 --notion
```

- `c1`: 벽을 반영한 최단거리로 필수 식당·배달지까지의 최대 거리 또는 MST 이동 하한을 계산한다.
- `c2`: 주문별 독립적인 최소 완료 시간을 주문 개수로 가중해 더하고 이동 하한과 큰 값을 쓴다. 싣기·배달 시간도 포함한다. 두 거리 휴리스틱의 비교는 우선 `c1`에서 한다.
- 탐색은 `env.successors(state, new_complaints=False)`를 사용한다. 현재 항의는 진행하지만 미래 신규 항의는 없다고 가정한다. 실제 게임의 항의 발생과 기본 확률 API는 그대로다. 휴리스틱은 항의 비용을 무시하므로 항의 우선 방문 정책은 아니다.
- `--replan never`가 기본이다. 처음 만든 계획을 그대로 실행한다. 실제 전이에서는 항상 3종 적재 금지를 지킨다.
- 팀 비교용 측정은 L2, 시드 0~99(설정별 100판)로 맞춘다. Python 버전, 측정일, 코드 버전, 재계획 모드도 기록한다. 개발 중 실행의 `+dirty` 표시는 미커밋 코드라는 뜻이다.
- 노드 수는 공통 탐색 API가 센다. `compute_mem_states`는 frontier, 부모 표, 휴리스틱 캐시에 저장한 레코드 수의 합의 최댓값이며 바이트 단위 메모리가 아니다. 허용성을 실행 중 검증하지 않으므로 `compute_h_violations`는 null이다.
- 로그를 특정 폴더에 `--out logs/greedy_review/greedy_L2.jsonl`처럼 저장했다면 요약에도 `python -m runner.summarize "logs/greedy_review/*.jsonl" --notion`처럼 해당 경로를 지정한다. 기본 요약은 하위 폴더까지 읽지 않는다.
- 원본 JSONL은 한 판 한 줄이다. `--notion --csv logs/notion_summary.csv`로 노션용 요약을 CSV로 저장할 수 있다. 최적격차는 같은 시드의 성공한 UCS 로그가 있어야 계산된다. 현재 요약기의 최적격차는 총비용(c1) 기준이다.

## A* 실행과 결과 확인

```powershell
python -m runner.run --agent astar --preset L2 --seeds 0-99 --param heuristic=mst --param objective=c1
python -m runner.run --agent astar --preset L2 --seeds 0-99 --param heuristic=constraint --param objective=c1
python -m runner.summarize --preset L2 --notion
```

- `max_distance`, `mst`는 Greedy와 같은 거리 하한이다. `c2`에서는 주문별 독립 최소 완료 시간 합과 큰 값을 사용한다.
- `constraint`는 MST 기반 하한과 작은 패턴 데이터베이스(PDB) 값 중 큰 값이다. 메뉴마다 주문 개수가 가장 많은 조합 하나씩(최대 3조합)을 남기고, 벽과 나머지 주문을 없앤 문제의 정확한 남은 비용을 사용한다. 남긴 주문의 적재 후 배달과 3종 금지를 유지한다. 추상 상태는 최대 3^3 × 8개이며 역방향 Dijkstra로 푼다.
- 실제 실행 경로는 완화 문제에서 같은 순서로 이동·적재·배달할 수 있고, 그 비용은 실제 비용 이하이다. 따라서 PDB도 하한이며, 두 하한의 최댓값도 하한이다. 작은 문제의 모든 도달 가능 상태에서 독립 최단경로 오라클로 과대추정 여부와 A* 해 비용을 검사한다(`tests/test_astar_agent.py`).
- 휴리스틱은 `agents.heuristics.DeliveryHeuristic(env, name, objective)`로 분리했다. IDA*에서도 호출할 수 있다. `heuristic=zero`는 검증용 UCS 동작이며 팀원의 UCS 구현을 대체하지 않는다.
- 같은 `f`는 작은 `h`부터, 그다음은 생성 순서로 처리한다. 더 작은 `g`를 발견하면 이미 확장한 상태도 다시 큐에 넣으며 오래된 큐 항목은 건너뛴다.
- 미래 신규 항의가 없는 결정적 모델을 사용한다. 현재 항의는 상태 전이에 반영하지만 휴리스틱은 항의 비용을 무시한다. L0·L1의 정적 문제와 L2·L3의 미래 항의를 무시한 계획 모델을 구분해야 한다. L2·L3 실제 확률 환경의 최적성을 주장하지 않는다.
- 노드 수는 실제 게임 모델을 탐색한 횟수다. PDB 전처리 노드는 포함하지 않으며 전처리 시간은 `compute_sec`에 포함한다. 저장 상태 지표는 frontier·best_g·부모 표·휴리스틱 캐시·PDB 값 표의 레코드 수 합의 최대다(전처리 임시 그래프와 바이트 메모리는 제외).
- 게임 실행 중 정확한 남은 비용을 매번 계산하지 않으므로 `compute_h_violations`는 null이다. 허용성 검증은 별도 테스트 결과로 기록하고, 최적격차는 L0·L1에서 동일 조건의 UCS 결과가 있을 때만 적는다.
- 설정별 100판을 별도 폴더에 저장했다면 `python -m runner.summarize "logs/astar_final/*.jsonl" --preset L2 --notion`으로 요약한다. 실험 로그는 로컬에만 보관한다.

## 한 번 계획 vs 매 스텝 재계획 (A* 기반)

```powershell
python -m runner.replanning --preset L2 --seeds 0-99 --heuristic mst --objective c1
python -m runner.summarize "logs/replanning_final/*.jsonl" --preset L2
```

- `runner.replanning`은 같은 A*, 휴리스틱, 목적함수, 프리셋, 시드, 판당 계산 제한으로 두 모드를 실행한다. 각 모드는 별도 프로세스에서 시작한다. 원본 로그의 알고리즘 이름은 둘 다 `astar`이고 `replan`으로 구분한다.
- `never`: 처음 전체 계획을 만들고 끝까지 실행한다. `every_step`: 행동을 고를 때마다 현재 관찰 상태에서 전체 계획을 새로 만든 뒤 첫 행동만 실행한다. 미래 항의 일정은 읽지 않는다. 현재 항의의 남은 시간과 초과 페널티는 전이에 반영한다.
- 기본은 L2, 시드 0~99(각 100판), MST, c1, 판당 계산시간 총합 60초다. `--objective c2`, `--heuristic constraint`, `--out-dir 경로`로 별도 조건도 실행할 수 있다. c2에는 항의 초과 페널티가 직접 포함되지 않는다.
- `logs/replanning_final/`에 모드별 JSONL, `L2_mst_c1_notion.csv`, `L2_mst_c1_comparison.json`을 저장한다. JSON에는 두 모드의 전체 지표와 같은 시드에서 비용이 감소/동일/증가한 판수가 있다. 비용 차이의 짝 비교는 두 방식 모두 성공한 판에서만 계산하고 실패 판수는 전체 지표에 남긴다.
- `compute_replans`는 최초 계획을 제외한다. 성공한 every_step 판에서는 실행한 행동 수 - 1이다. `compute_nodes_expanded`와 `compute_sec`는 모든 재계획을 합친 판당 값이다. 계산시간 제한도 판 전체에 누적 적용한다.
- `compute_plan_len`은 마지막으로 만든 계획 길이다. every_step에서는 마지막 행동 직전의 짧은 계획이 남으므로 최초 전체 계획 길이와 직접 비교하지 않는다.
- 기존 `runner.summarize --vs astar astar`는 재계획 모드를 구분하지 못하므로 이 비교에 사용하지 않는다. 위의 전용 비교 JSON 또는 모드별 요약 표를 사용한다. 기본 로그 요약은 하위 폴더를 자동으로 읽지 않으므로 경로를 지정한다.

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

## 파트 B 검증 도구 (조진수)

별도 검증 브랜치에서 작업하며 main이나 다른 팀원의 브랜치에 직접 push하지 않는다.

```powershell
# B1: 기록된 행동열 재생 + 별도 산식/집계 검산 (독립 시뮬레이터 아님)
python -m verify.b1_metrics logs/greedy_final logs/astar_final logs/replanning_final --out logs/runs/20261117/b/b1_metrics.json

# B2: 400개 시나리오 구조·분포와 A* 비용 이상치
python -m verify.b2_scenarios --outlier-logs "logs/astar_final/L1_*_c1.jsonl" --out logs/runs/20261117/b/b2_scenarios.json

# B3: 실제 크기 L0/L1, 두 목적함수, 팀원 UCS와 A* 3종 등 교차 검사
python -m verify.b3_algorithms --seeds 0-9 --out-dir logs/runs/20261117/b/b3

# 반복 심화는 memo=true 변형임을 명시하고 별도 실행
python -m verify.b3_algorithms --presets L1 --seeds 0-2 --include-iterative --out-dir logs/runs/20261117/b/b3_iterative

# B1-b: 한 번에 하나만 실행. 5회 반복 CV, 외부 계측, 순서/캐시 진단
python -m verify.b1_timing --param heuristic=mst --param objective=c1 --out logs/runs/20261117/b/b1_timing.json
```

- B3/타이밍은 미커밋 코드에서 실행을 거부한다. 결과 JSON에 날짜, 커밋, Python, OS, 기계 식별을 남긴다.
- B1은 현재 공용 DeliveryEnv로 행동열을 재생하고 총비용·완료시각 합·미완료 H 처리·전체 합산 비율·나쁜 10% 평균을 별도 산식으로 확인한다. 전이/사건 판정은 원래 환경을 공유하므로 명세 기반 독립 구현의 증거가 아니다. 비용을 일부러 바꾼 로그를 거부하는 테스트도 있다.
- B1 독립 시뮬레이터는 상세 규칙 명세와 그 구현을 읽지 않은 별도 작성자가 필요하다. 이 대화는 기존 규칙 구현을 읽은 이력이 있어 독립성을 주장하지 않는다. B1 도구가 불일치 0건이어도 전체 판정은 conditional이다.
- B2는 생성기 일치(A1)와 별개인 내용 검사다. 분포의 근사 3SE 경고는 탐색적 경고이며, 다중 비교/메뉴 포함 조건 때문에 단독으로 버그를 입증하지 않는다. 이상치는 같은 설정·커밋끼리의 IQR 1.5배 기준으로 목록화한다.
- B3는 같은 목적함수에서만 성공한 UCS와 A*/IDA* 결과를 비교한다(c2는 같은 판의 평균배달시간으로 비교해도 동일). 미완료 판은 숨기지 않고 따로 기록한다. 공통 환경의 규칙 오류는 이 비교만으로 검증되지 않는다. 검증 담당 조진수·팀원1이 교차 확인하며 별도의 비구현자 리뷰는 필수 범위에서 제외한다(2026-11-17 사용자 결정).
- CSP 원본은 main 미등록이며 담당자 브랜치를 직접 수정하지 않는다. 수정 제안과 동결 원본은 아래의 별도 모듈로 관리한다. 공식 에이전트 통합은 담당자와 별도 결정한다.
- 타이밍 도구는 계측 래퍼의 오버헤드가 있으므로 실제 성능표에 섞지 않는다. CV가 10%를 넘으면 해당 조건의 시간 안정성은 통과로 쓰지 않는다.
- JSON 판정은 pass/conditional/fail이다. 통과한 범위와 미검증 범위를 나눠 보고하고, 최종 발표용 재실행은 검토 후 병합된 코드에서 한다.

### CSP 반례와 수정 제안

- 원본: `feature/csp` 커밋 `d9fb289`, `agents/csp_agent.py`의 Git blob `56e412b07f8ab87e2c544da959557dd3b943f592`를 `verify/fixtures/csp_d9fb289.py`에 동결했다. 원본 보존 검사를 포함한다.
- 반례 1: 김치·피자를 이미 적재한 상태에서 탕수육 적재를 제약 검사 함수가 허용한다.
- 반례 2: 피자·탕수육을 이미 적재하고 김치 식당에 있는 상태에서 원본 에이전트가 실제로 부적법한 LOAD를 선택한다.
- 제안 구현: `verify/csp_candidate.py:CSPCandidateAgent`. 현재 적재 상태와 일괄 LOAD/DELIVER를 반영하고, 부분 배정은 확정된 연속 접두부만 검사해 정상 해를 성급히 제거하지 않는다.
- MRV/FC/백트래킹은 원본을 유지한다. 부분 배정 검사 완화로 탐색이 늘지 않도록, 이미 적재한 주문 배달 -> 식당별 P 묶음 -> D 묶음인 실행 가능한 기본 순서의 값을 먼저 시도한다. 비용 최적화나 거리 기반 방문 순서 개선이라고 주장하지 않는다.
- 재계획 설정과 시간 제한 검사를 적용한다. 해가 없거나 계획이 부적법하면 CSPPlanError를 내며 임의의 UP 행동으로 숨기지 않는다. REGISTRY에는 후보를 자동 등록하지 않는다.
- 회귀 검사: `python -m pytest -q tests/test_csp_candidate.py`. 전체 대기 720개, 부분 적재 24개 작업 순서를 공용 환경의 합법 행동과 비교한다. 이 비교는 독립 규칙 구현이 아니다.
- 실제 판 재검증: `python -m verify.b3_csp_recheck --out-dir logs/runs/20261117/b/csp_candidate`. L0~L3 각 100판과 L2의 재계획/FC-off 진단 각 10판을 수행한다. 모든 결과는 수정 후보의 결과이며 원본 전체 성능 결과로 사용하지 않는다.
- 상세 규칙 명세는 2026-11-18 수령 후 별도 검증을 진행할 예정이며, 그 전까지 명세 기반 독립 시뮬레이터는 미완료로 남긴다.
