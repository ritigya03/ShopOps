import pytest
from fastapi import HTTPException

from app.auth import CurrentUser
from app.guardrails import InsufficientEvidenceError, assert_evidence_present, require_permission
from app.schemas import PolicyEvidence


def test_require_permission_allows_role_that_has_it():
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="OperationsManager")
    assert dependency(current_user=user) == user


def test_require_permission_rejects_role_without_it():
    dependency = require_permission("can_view_seller_metrics")
    user = CurrentUser(sub="1", email="a@b.com", role="Viewer")
    with pytest.raises(HTTPException) as exc_info:
        dependency(current_user=user)
    assert exc_info.value.status_code == 403


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
