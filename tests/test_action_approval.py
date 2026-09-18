import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.tools import calculate_compensation

client = TestClient(app)
pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_proposal(engine, order_id="33a3edb84b9df4cb49546859b990ac6d", expired=False):
    proposal = calculate_compensation(order_id)
    assert proposal is not None and proposal.eligible
    payload_hash = hashlib.sha256(
        f"{order_id}:{proposal.proposed_amount}:{proposal.policy_version}".encode()
    ).hexdigest()
    interval_sql = "now() - interval '1 hour'" if expired else "now() + interval '24 hours'"
    with engine.begin() as conn:
        row = conn.execute(text(f"""
            INSERT INTO shopops_ops.action_requests
                (action_type, order_id, payload_hash, status, requested_by, idempotency_key, policy_version, expires_at)
            VALUES ('compensation_proposal', :order_id, :payload_hash, 'PROPOSED', 'test-requester',
                    :idempotency_key, :policy_version, {interval_sql})
            RETURNING action_id
        """), {
            "order_id": order_id, "payload_hash": payload_hash,
            "idempotency_key": str(uuid.uuid4()), "policy_version": proposal.policy_version,
        }).mappings().first()
    return str(row["action_id"]), proposal.proposed_amount


def test_approve_happy_path(engine, cognito_tokens):
    action_id, amount = _create_proposal(engine)

    resp = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "SUCCEEDED"
    assert float(body["proposed_amount"]) == float(amount)


def test_reject(engine, cognito_tokens):
    action_id, _ = _create_proposal(engine)

    resp = client.post(f"/actions/{action_id}/reject", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    assert resp.json()["status"] == "REJECTED"


def test_double_approve_is_idempotent(engine, cognito_tokens):
    action_id, _ = _create_proposal(engine)

    resp1 = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))
    resp2 = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["proposed_amount"] == resp2.json()["proposed_amount"]


def test_expired_proposal_returns_409(engine, cognito_tokens):
    action_id, _ = _create_proposal(engine, expired=True)

    resp = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 409


def test_reject_then_approve_returns_409(engine, cognito_tokens):
    action_id, _ = _create_proposal(engine)
    client.post(f"/actions/{action_id}/reject", headers=_auth(cognito_tokens["OperationsManager"]))

    resp = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 409


def test_non_manager_denied_and_audited(engine, cognito_tokens):
    action_id, _ = _create_proposal(engine)
    before = datetime.now(timezone.utc)

    resp = client.post(f"/actions/{action_id}/approve", headers=_auth(cognito_tokens["SupportAgent"]))

    assert resp.status_code == 403
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT outcome FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND tool_name = 'can_approve_compensation'
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before}).mappings().first()
    assert row is not None
    assert row["outcome"] == "denied"


def test_approve_missing_action_returns_404(cognito_tokens):
    resp = client.post(f"/actions/{uuid.uuid4()}/approve", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 404
