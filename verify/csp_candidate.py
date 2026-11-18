"""Compatibility alias for historical correction experiments."""
from agents.csp_agent import CSPAgent, CSPPlanError


class CSPCandidateAgent(CSPAgent):
    name = "csp_candidate"
