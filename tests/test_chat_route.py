from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)
pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_order_status_inquiry(cognito_tokens):
    resp = client.post(
        "/chat",
        json={"message": "What is the status of order 00010242fe8c5a6d1ba2dd792cb16214?"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"]
    assert "delivered" in body["answer"].lower()


def test_delayed_order_compensation_proposal(cognito_tokens):
    resp = client.post(
        "/chat",
        json={"message": "Order 33a3edb84b9df4cb49546859b990ac6d was delivered late, can you propose compensation?"},
        headers=_auth(cognito_tokens["SupportAgent"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["proposal"] is not None
    assert body["action_id"] is not None
    assert body["proposal"]["severity"] == "moderate"


def test_seller_metrics_denied_for_viewer_is_audited(cognito_tokens, engine):
    before = datetime.now(timezone.utc)
    resp = client.post(
        "/chat",
        json={"message": "What's the late delivery rate for seller 48436dade18ac8b2bce089ec2a041202?"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT outcome FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND tool_name = 'get_seller_metrics'
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before}).mappings().first()
    assert row is not None
    assert row["outcome"] == "denied"


def test_chat_without_token_is_rejected():
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_conversation_persists_across_turns(cognito_tokens):
    resp1 = client.post(
        "/chat", json={"message": "What is the status of order 00010242fe8c5a6d1ba2dd792cb16214?"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    conversation_id = resp1.json()["conversation_id"]

    resp2 = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "What order ID did I just ask about? Just the ID."},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp2.status_code == 200
    assert "00010242fe8c5a6d1ba2dd792cb16214" in resp2.json()["answer"]


def test_conversation_owned_by_another_user_is_rejected(cognito_tokens):
    resp1 = client.post("/chat", json={"message": "hello"}, headers=_auth(cognito_tokens["Viewer"]))
    conversation_id = resp1.json()["conversation_id"]

    resp2 = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "hello again"},
        headers=_auth(cognito_tokens["SupportAgent"]),
    )
    assert resp2.status_code == 403


def test_unknown_conversation_id_returns_404(cognito_tokens):
    resp = client.post(
        "/chat",
        json={"conversation_id": "00000000-0000-0000-0000-000000000000", "message": "hi"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 404
