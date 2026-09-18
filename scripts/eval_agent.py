from pathlib import Path

import yaml

from app.agent.graph import AGENT_GRAPH
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.auth import CurrentUser


def load_cases(path: Path) -> list[dict]:
    with path.open() as f:
        return yaml.safe_load(f)


def score_tool_selection(case: dict, result: dict) -> bool:
    return set(result["actual_tools"]) == set(case.get("expected_tools", []))


def score_citation(case: dict, result: dict) -> bool | None:
    expected_doc_id = case.get("expected_citation_doc_id")
    if expected_doc_id is None:
        return None
    return expected_doc_id in result["actual_citation_doc_ids"]


def score_abstention(case: dict, result: dict) -> bool:
    return result["actual_abstain"] == case.get("expect_abstain", False)


def _build_eval_state(case: dict) -> AgentState:
    user = CurrentUser(sub="eval", email="eval@shopops.test", role=case["role"])
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["message"]},
        ],
        "user": user,
        "pending_tool_calls": [],
        "tool_results": [],
        "evidence": [],
        "abstain": False,
        "loop_count": 0,
        "answer": None,
        "proposal": None,
    }


def run_case(case: dict) -> dict:
    state = _build_eval_state(case)
    result = AGENT_GRAPH.invoke(state)
    return {
        "case_id": case["id"],
        "message": case["message"],
        "actual_tools": [tr["tool_name"] for tr in result["tool_results"]],
        "actual_citation_doc_ids": [e.doc_id for e in result["evidence"]],
        "actual_abstain": result["abstain"],
        "answer": result["answer"],
    }
