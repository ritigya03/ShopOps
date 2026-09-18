from app.agent.prompts import SYSTEM_PROMPT
from scripts.eval_agent import (
    _build_eval_state,
    load_cases,
    score_abstention,
    score_citation,
    score_tool_selection,
)


def test_load_cases_parses_yaml(tmp_path):
    cases_file = tmp_path / "cases.yaml"
    cases_file.write_text("""
- id: sample_case
  message: "hello"
  role: Viewer
  expected_tools: [get_order]
""")
    cases = load_cases(cases_file)
    assert cases == [{"id": "sample_case", "message": "hello", "role": "Viewer", "expected_tools": ["get_order"]}]


def test_score_tool_selection_matches_exact_set():
    case = {"expected_tools": ["get_order", "estimate_delivery_risk"]}
    result = {"actual_tools": ["estimate_delivery_risk", "get_order"]}
    assert score_tool_selection(case, result) is True


def test_score_tool_selection_detects_mismatch():
    case = {"expected_tools": ["get_order"]}
    result = {"actual_tools": ["get_seller_metrics"]}
    assert score_tool_selection(case, result) is False


def test_score_tool_selection_defaults_to_empty_expected():
    case = {}
    result = {"actual_tools": []}
    assert score_tool_selection(case, result) is True


def test_score_citation_returns_none_when_not_applicable():
    case = {}
    result = {"actual_citation_doc_ids": ["POL-COMP-001"]}
    assert score_citation(case, result) is None


def test_score_citation_matches_expected_doc_id():
    case = {"expected_citation_doc_id": "POL-COMP-001"}
    result = {"actual_citation_doc_ids": ["POL-DELIVERY-001", "POL-COMP-001"]}
    assert score_citation(case, result) is True


def test_score_citation_detects_missing_doc_id():
    case = {"expected_citation_doc_id": "POL-COMP-001"}
    result = {"actual_citation_doc_ids": ["POL-DELIVERY-001"]}
    assert score_citation(case, result) is False


def test_score_abstention_matches_expected_true():
    case = {"expect_abstain": True}
    result = {"actual_abstain": True}
    assert score_abstention(case, result) is True


def test_score_abstention_defaults_to_expected_false():
    case = {}
    result = {"actual_abstain": False}
    assert score_abstention(case, result) is True


def test_score_abstention_detects_mismatch():
    case = {"expect_abstain": True}
    result = {"actual_abstain": False}
    assert score_abstention(case, result) is False


def test_build_eval_state_shapes_initial_agent_state():
    case = {"message": "What is the status of order abc123?", "role": "SupportAgent"}
    state = _build_eval_state(case)

    assert state["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "What is the status of order abc123?"},
    ]
    assert state["user"].sub == "eval"
    assert state["user"].role == "SupportAgent"
    assert state["pending_tool_calls"] == []
    assert state["tool_results"] == []
    assert state["evidence"] == []
    assert state["abstain"] is False
    assert state["loop_count"] == 0
    assert state["answer"] is None
    assert state["proposal"] is None
