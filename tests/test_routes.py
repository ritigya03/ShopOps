from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_get_order_accessible_to_viewer(cognito_tokens):
    resp = client.get("/orders/00010242fe8c5a6d1ba2dd792cb16214", headers=_auth(cognito_tokens["Viewer"]))
    assert resp.status_code == 200
    assert resp.json()["order_status"] == "delivered"


def test_get_order_without_token_is_rejected():
    resp = client.get("/orders/00010242fe8c5a6d1ba2dd792cb16214")
    assert resp.status_code == 401


def test_seller_metrics_forbidden_for_viewer(cognito_tokens):
    resp = client.get(
        "/sellers/48436dade18ac8b2bce089ec2a041202/metrics",
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 403


def test_seller_metrics_allowed_for_manager(cognito_tokens):
    resp = client.get(
        "/sellers/48436dade18ac8b2bce089ec2a041202/metrics",
        headers=_auth(cognito_tokens["OperationsManager"]),
    )
    assert resp.status_code == 200


def test_policy_search_returns_citations(cognito_tokens):
    resp = client.get(
        "/policy/search", params={"query": "late delivery compensation"},
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()) > 0
    assert "doc_id" in resp.json()[0]


def test_delivery_risk_accessible_to_support_agent(cognito_tokens):
    # 00010242fe8c5a6d1ba2dd792cb16214 is on-time (verified in Task 5).
    resp = client.get(
        "/orders/00010242fe8c5a6d1ba2dd792cb16214/risk",
        headers=_auth(cognito_tokens["SupportAgent"]),
    )
    assert resp.status_code == 200
    assert resp.json()["is_late"] is False


def test_compensation_proposal_accessible_to_support_agent(cognito_tokens):
    # 33a3edb84b9df4cb49546859b990ac6d is a real moderate-delay order,
    # order_value 67.50, verified live in Task 5.
    resp = client.get(
        "/orders/33a3edb84b9df4cb49546859b990ac6d/compensation",
        headers=_auth(cognito_tokens["SupportAgent"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible"] is True
    assert body["severity"] == "moderate"


def test_get_order_not_found_returns_404(cognito_tokens):
    resp = client.get("/orders/does-not-exist", headers=_auth(cognito_tokens["Viewer"]))
    assert resp.status_code == 404


def test_get_order_writes_audit_event(cognito_tokens, engine):
    # Confirms _log_audit actually persists a row — every other test here
    # only confirms the HTTP response, not the audit trail §3.3 requires.
    before = datetime.now(timezone.utc)
    resp = client.get(
        "/orders/00010242fe8c5a6d1ba2dd792cb16214",
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 200

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT outcome, role_snapshot FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND tool_name = 'get_order'
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before}).mappings().first()
    assert row is not None
    assert row["outcome"] == "success"
    assert row["role_snapshot"] == "Viewer"


def test_seller_metrics_denial_is_audited(cognito_tokens, engine):
    before = datetime.now(timezone.utc)
    resp = client.get(
        "/sellers/48436dade18ac8b2bce089ec2a041202/metrics",
        headers=_auth(cognito_tokens["Viewer"]),
    )
    assert resp.status_code == 403
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT outcome, role_snapshot FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND tool_name = 'can_view_seller_metrics'
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before}).mappings().first()
    assert row is not None
    assert row["outcome"] == "denied"
    assert row["role_snapshot"] == "Viewer"
