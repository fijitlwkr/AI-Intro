"""알고리즘 등록. 새 알고리즘은 파일을 만들고 아래 REGISTRY에 한 줄을 더한다."""
from .random_agent import RandomAgent
from .rule_agent import RuleAgent
from .logic_agent import LogicAgent
from .greedy_agent import GreedyAgent

REGISTRY = {
    "random": RandomAgent,
    "rule": RuleAgent,
    "logic": LogicAgent,
    "greedy": GreedyAgent,
}
