import json
from unittest.mock import Mock

import pytest

from app.agent.graph import AGENT_GRAPH
from app.agent.nodes import propose_or_finalize, validate_evidence
from app.agent.state import AgentState
from app.auth import CurrentUser
from app.schemas import PolicyEvidence

pytestmark = pytest.mark.integration


def _fake_response(content=None, tool_calls=None):
    message = Mock(content=content, tool_calls=tool_calls)
    return Mock(choices=[Mock(message=message)])


def _fake_tool_call(call_id, name, args):
    # Mock(name=...) is a reserved constructor kwarg (sets repr, not an
    # attribute) - assign .name as a plain attribute afterward instead.
    fn = Mock()
    fn.name = name
    fn.arguments = json.dumps(args)
    return Mock(id=call_id, function=fn)


def _initial_state(role: str, message: str) -> AgentState:
    return {
        "messages": [
            {"role": "system", "content": "test system prompt"},
            {"role": "user", "content": message},
        ],
        "user": CurrentUser(sub="test-sub", email="test@example.com", role=role),
        "pending_tool_calls": [],
        "tool_results": [],
        "evidence": [],
        "abstain": False,
        "loop_count": 0,
        "answer": None,
        "proposal": None,
    }


def test_routes_to_get_order_tool_and_synthesizes_answer(monkeypatch):
    responses = iter([
        _fake_response(tool_calls=[_fake_tool_call("call_1", "get_order", {"order_id": "00010242fe8c5a6d1ba2dd792cb16214"})]),
        _fake_response(content="Order 00010242fe8c5a6d1ba2dd792cb16214 is delivered."),
    ])
    monkeypatch.setattr("app.agent.nodes.call_model", lambda *a, **kw: next(responses))

    result = AGENT_GRAPH.invoke(_initial_state("Viewer", "Where is order 00010242fe8c5a6d1ba2dd792cb16214?"))

    assert result["tool_results"][0]["tool_name"] == "get_order"
    assert result["tool_results"][0]["error"] is None
    assert "delivered" in result["answer"]


def test_denied_tool_call_is_audited_not_crashed(monkeypatch):
    responses = iter([
        _fake_response(tool_calls=[_fake_tool_call("call_1", "get_seller_metrics", {"seller_id": "48436dade18ac8b2bce089ec2a041202"})]),
        _fake_response(content="I don't have permission to check that."),
    ])
    monkeypatch.setattr("app.agent.nodes.call_model", lambda *a, **kw: next(responses))

    result = AGENT_GRAPH.invoke(_initial_state("Viewer", "What are this seller's metrics?"))

    assert result["tool_results"][0]["error"] == "permission_denied"
    assert result["answer"]


def test_loop_bound_stops_after_two_rounds(monkeypatch):
    def always_request_tool(*a, **kw):
        return _fake_response(tool_calls=[_fake_tool_call("call_x", "get_order", {"order_id": "00010242fe8c5a6d1ba2dd792cb16214"})])
    monkeypatch.setattr("app.agent.nodes.call_model", always_request_tool)

    result = AGENT_GRAPH.invoke(_initial_state("Viewer", "Tell me everything, keep going forever."))

    assert result["loop_count"] == 2
    assert len(result["tool_results"]) == 2
    assert result["answer"] is not None  # forced into synthesis, not stuck looping


def test_validate_evidence_sets_abstain_when_no_evidence_meets_threshold():
    state = _initial_state("Viewer", "irrelevant")
    state["evidence"] = [PolicyEvidence(doc_id="POL-X", version="1.0", section="1", excerpt="irrelevant", score=0.05)]

    result = validate_evidence(state)

    assert result["abstain"] is True


def test_validate_evidence_passes_when_evidence_meets_threshold():
    state = _initial_state("Viewer", "irrelevant")
    state["evidence"] = [PolicyEvidence(doc_id="POL-X", version="1.0", section="1", excerpt="relevant", score=0.9)]

    result = validate_evidence(state)

    assert result["abstain"] is False


def test_validate_evidence_no_evidence_gathered_does_not_abstain():
    state = _initial_state("Viewer", "irrelevant")
    state["evidence"] = []

    result = validate_evidence(state)

    assert result["abstain"] is False


def test_propose_or_finalize_creates_action_request_row(engine):
    from sqlalchemy import text

    state = _initial_state("SupportAgent", "irrelevant")
    state["tool_results"] = [{
        "tool_name": "calculate_compensation",
        "args": {"order_id": "33a3edb84b9df4cb49546859b990ac6d"},
        "result": {
            "order_id": "33a3edb84b9df4cb49546859b990ac6d", "eligible": True,
            "reason": "late", "policy_doc_id": "POL-COMP-001", "policy_version": "1.0",
            "severity": "moderate", "compensation_percentage": 0.25,
            "order_value": "67.50", "proposed_amount": "16.875", "cap_applied": False,
        },
        "error": None,
    }]

    result = propose_or_finalize(state)

    assert result["proposal"] is not None
    action_id = result["proposal"]["action_id"]
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status, requested_by, order_id FROM shopops_ops.action_requests WHERE action_id = :id"
        ), {"id": action_id}).mappings().first()
    assert row["status"] == "PROPOSED"
    assert row["requested_by"] == "test-sub"
    assert row["order_id"] == "33a3edb84b9df4cb49546859b990ac6d"


def test_propose_or_finalize_skips_when_role_lacks_permission():
    state = _initial_state("Viewer", "irrelevant")
    state["tool_results"] = [{
        "tool_name": "calculate_compensation", "args": {},
        "result": {"order_id": "x", "eligible": True, "proposed_amount": "10", "policy_version": "1.0"},
        "error": None,
    }]

    result = propose_or_finalize(state)

    assert result["proposal"] is None


def test_propose_or_finalize_skips_when_abstained():
    state = _initial_state("SupportAgent", "irrelevant")
    state["abstain"] = True
    state["tool_results"] = [{
        "tool_name": "calculate_compensation", "args": {},
        "result": {"order_id": "x", "eligible": True, "proposed_amount": "10", "policy_version": "1.0"},
        "error": None,
    }]

    result = propose_or_finalize(state)

    assert result["proposal"] is None
