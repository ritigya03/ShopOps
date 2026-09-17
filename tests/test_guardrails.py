import pytest
from fastapi import HTTPException
from unittest.mock import Mock

import app.guardrails as guardrails_module
from app.auth import CurrentUser
from app.guardrails import (
    InsufficientEvidenceError,
    assert_evidence_present,
    require_permission,
)
from app.schemas import PolicyEvidence


@pytest.fixture(autouse=True)
def _no_audit_db_calls(monkeypatch):
    # require_permission's denial branch now calls log_audit (Fix 2), which
    # opens a real DB connection. These tests exercise pure permission
    # logic and must stay network-free; the audit-on-denial behavior
    # itself is covered against a real DB by
    # test_routes.py::test_seller_metrics_denial_is_audited.
    mock = Mock()
    monkeypatch.setattr(guardrails_module, "log_audit", mock)
    return mock


def test_require_permission_allows_role_that_has_it(_no_audit_db_calls):
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="OperationsManager")
    assert dependency(current_user=user) == user
    _no_audit_db_calls.assert_not_called()


def test_require_permission_rejects_role_without_it(_no_audit_db_calls):
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="Viewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency(current_user=user)
    assert exc_info.value.status_code == 403
    _no_audit_db_calls.assert_called_once_with(user, "can_view_seller_metrics", "denied")


def test_support_agent_can_propose_compensation_but_not_view_seller_metrics():
    user = CurrentUser(sub="1", email="a@b.com", role="SupportAgent")
    assert require_permission("can_propose_compensation")(current_user=user) == user
    with pytest.raises(HTTPException):
        require_permission("can_view_seller_metrics")(current_user=user)


def test_assert_evidence_present_raises_when_empty():
    with pytest.raises(InsufficientEvidenceError):
        assert_evidence_present([])


def test_assert_evidence_present_raises_when_all_low_score():
    low = [PolicyEvidence(doc_id="X", version="1.0", section="s", excerpt="e", score=0.1)]
    with pytest.raises(InsufficientEvidenceError):
        assert_evidence_present(low, min_score=0.3)


def test_viewer_can_view_order_and_search_policy():
    # Viewer's actual allow path — the tests above only ever exercise
    # Viewer as a deny case via can_view_seller_metrics.
    user = CurrentUser(sub="1", email="a@b.com", role="Viewer")
    assert require_permission("can_view_order")(current_user=user) == user
    assert require_permission("can_search_policy")(current_user=user) == user


def test_unrecognized_role_denies_every_permission():
    # PERMISSIONS.get(role, set()) must fail closed for a role string that
    # isn't one of the three known roles, not raise or silently allow.
    user = CurrentUser(sub="1", email="a@b.com", role="SomeUnknownRole")
    with pytest.raises(HTTPException) as exc_info:
        require_permission("can_view_order")(current_user=user)
    assert exc_info.value.status_code == 403


def test_assert_evidence_present_filters_out_low_score_entries():
    # Confirms the *returned* list actually drops weak matches, not just
    # that a strong-enough list doesn't raise.
    mixed = [
        PolicyEvidence(doc_id="A", version="1.0", section="s1", excerpt="strong", score=0.8),
        PolicyEvidence(doc_id="B", version="1.0", section="s2", excerpt="weak", score=0.1),
    ]
    result = assert_evidence_present(mixed, min_score=0.3)
    assert [e.doc_id for e in result] == ["A"]
