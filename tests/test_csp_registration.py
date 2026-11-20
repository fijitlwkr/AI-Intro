import ast
from pathlib import Path

from agents import CSPAgent, REGISTRY
from runner.run import resolve_agent
from verify.csp_candidate import CSPCandidateAgent


def test_csp_is_registered_for_standard_runner():
    assert REGISTRY["csp"] is CSPAgent
    assert resolve_agent("csp") is CSPAgent
    assert CSPAgent().name == "csp"
    assert isinstance(CSPCandidateAgent(), CSPAgent)


def test_production_csp_has_no_dependency_on_verification_fixtures():
    path = Path(__file__).resolve().parents[1] / "agents/csp_agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m and (m.startswith("verify") or m.startswith("tests")) for m in modules)
