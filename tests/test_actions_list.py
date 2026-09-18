import hashlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.tools import calculate_compensation

client = TestClient(app)
pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_proposal(engine, order_id="33a3edb84b9df4cb49546859b990ac6d"):
    proposal = calculate_compensation(order_id)
    assert proposal is not None and proposal.eligible
    payload_hash = hashlib.sha256(
        f"{order_id}:{proposal.proposed_amount}:{proposal.policy_version}".encode()
    ).hexdigest()
    with engine.begin() as conn:
        row = conn.execute(text("""
            INSERT INTO shopops_ops.action_requests
                (action_type, order_id, payload_hash, status, requested_by, idempotency_key, policy_version, expires_at)
            VALUES ('compensation_proposal', :order_id, :payload_hash, 'PROPOSED', 'test-requester',
                    :idempotency_key, :policy_version, now() + interval '24 hours')
            RETURNING action_id
        """), {
            "order_id": order_id, "payload_hash": payload_hash,
            "idempotency_key": str(uuid.uuid4()), "policy_version": proposal.policy_version,
        }).mappings().first()
    return str(row["action_id"])


def test_list_pending_actions_includes_new_proposal(engine, cognito_tokens):
    action_id = _create_proposal(engine)

    resp = client.get("/actions", params={"status": "PROPOSED"}, headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    body = resp.json()
    match = next((a for a in body if a["action_id"] == action_id), None)
    assert match is not None
    assert match["status"] == "PROPOSED"
    assert match["is_expired"] is False
    assert match["proposed_amount"] is not None
    assert match["reason"]


def test_list_succeeded_actions_after_approval(engine, cognito_tokens):
    action_id = _create_proposal(engine)
    client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    resp = client.get("/actions", params={"status": "SUCCEEDED"}, headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    match = next((a for a in resp.json() if a["action_id"] == action_id), None)
    assert match is not None
    assert match["status"] == "SUCCEEDED"
    assert match["approved_by"] is not None
    assert match["proposed_amount"] is not None


def test_list_actions_denied_for_non_manager(cognito_tokens):
    resp = client.get("/actions", headers=_auth(cognito_tokens["SupportAgent"]))

    assert resp.status_code == 403
