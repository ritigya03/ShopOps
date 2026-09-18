import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
pytestmark = pytest.mark.integration


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_audit_events_includes_recent_activity(cognito_tokens):
    # Generate a known event first.
    client.get(
        "/orders/00010242fe8c5a6d1ba2dd792cb16214",
        headers=_auth(cognito_tokens["Viewer"]),
    )

    resp = client.get("/audit-events", headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) > 0
    assert any(e["tool_name"] == "get_order" for e in body)


def test_list_audit_events_respects_limit(cognito_tokens):
    resp = client.get("/audit-events", params={"limit": 2}, headers=_auth(cognito_tokens["OperationsManager"]))

    assert resp.status_code == 200
    assert len(resp.json()) <= 2


def test_list_audit_events_denied_for_non_manager(cognito_tokens):
    resp = client.get("/audit-events", headers=_auth(cognito_tokens["SupportAgent"]))

    assert resp.status_code == 403
