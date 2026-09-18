import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)
pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(response) -> list[tuple[str, object]]:
    # Every event's data line is JSON-encoded (see app/routes.py's
    # _sse_event) - a raw multi-line chunk (e.g. a paragraph break in the
    # model's answer) would otherwise break SSE framing.
    events = []
    event_name = None
    for line in response.iter_lines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            events.append((event_name, json.loads(line.removeprefix("data: "))))
    return events


def test_stream_order_status_inquiry(cognito_tokens):
    with client.stream(
        "POST", "/chat/stream",
        json={"message": "What is the status of order 00010242fe8c5a6d1ba2dd792cb16214?"},
        headers=_auth(cognito_tokens["Viewer"]),
    ) as resp:
        assert resp.status_code == 200
        events = _parse_sse(resp)

    chunk_events = [d for name, d in events if name == "chunk"]
    done_events = [d for name, d in events if name == "done"]
    error_events = [d for name, d in events if name == "error"]

    assert not error_events
    assert len(chunk_events) >= 1
    assert len(done_events) == 1

    full_answer = "".join(chunk_events)
    assert "delivered" in full_answer.lower()

    done_payload = done_events[0]
    assert done_payload["conversation_id"]
    assert done_payload["proposal"] is None
    assert done_payload["action_id"] is None


def test_stream_conversation_persists_and_is_loadable_via_chat(cognito_tokens):
    with client.stream(
        "POST", "/chat/stream",
        json={"message": "What is the status of order 00010242fe8c5a6d1ba2dd792cb16214?"},
        headers=_auth(cognito_tokens["Viewer"]),
    ) as resp:
        events = _parse_sse(resp)
    conversation_id = next(d for name, d in events if name == "done")["conversation_id"]

    resp = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "What order ID did I just ask about? Just the ID."},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200
    assert "00010242fe8c5a6d1ba2dd792cb16214" in resp.json()["answer"]


def test_stream_without_token_is_rejected():
    with client.stream("POST", "/chat/stream", json={"message": "hi"}) as resp:
        assert resp.status_code == 401


def test_stream_failure_mid_answer_sends_error_and_does_not_persist(cognito_tokens, engine, monkeypatch):
    # Forces the loop-bound forced-stop path (same technique as
    # test_agent_graph.py's test_loop_bound_stops_after_two_rounds): the
    # model requests a tool on both allowed rounds, so routed["answer"]
    # is never set by route_or_tools and ROUTING_GRAPH.invoke() lands in
    # the streaming branch deterministically, with zero real Gemini calls.
    def always_request_tool(*a, **kw):
        fn = Mock()
        fn.name = "get_order"
        fn.arguments = json.dumps({"order_id": "00010242fe8c5a6d1ba2dd792cb16214"})
        tool_call = Mock(id="call_x", function=fn)
        message = Mock(content=None, tool_calls=[tool_call])
        return Mock(choices=[Mock(message=message)])

    def broken_stream(*args, **kwargs):
        yield "partial answer that should never be saved"
        raise RuntimeError("simulated LLM failure")

    monkeypatch.setattr("app.agent.nodes.call_model", always_request_tool)
    monkeypatch.setattr("app.routes.stream_model", broken_stream)

    with client.stream(
        "POST", "/chat/stream",
        json={"message": "irrelevant, routing is mocked"},
        headers=_auth(cognito_tokens["Viewer"]),
    ) as resp:
        events = _parse_sse(resp)

    error_events = [d for name, d in events if name == "error"]
    done_events = [d for name, d in events if name == "done"]
    assert len(error_events) == 1
    assert not done_events

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT 1 FROM shopops_ops.conversation_messages WHERE content LIKE '%should never be saved%'
        """)).first()
    assert row is None
