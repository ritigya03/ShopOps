import pytest
from fastapi.testclient import TestClient

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
