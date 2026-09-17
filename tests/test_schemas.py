import pytest
from pydantic import ValidationError

from app.schemas import CompensationProposal, PolicyEvidence, RiskAssessment


def test_policy_evidence_requires_score_between_0_and_1():
    evidence = PolicyEvidence(
        doc_id="POL-COMP-001", version="1.0", section="3. Compensation tiers",
        excerpt="...", score=0.53,
    )
    assert evidence.score == 0.53


def test_policy_evidence_rejects_score_above_1():
    with pytest.raises(ValidationError):
        PolicyEvidence(doc_id="X", version="1.0", section="s", excerpt="e", score=1.5)


def test_risk_assessment_optional_fields_default_to_none_when_omitted():
    # An on-time order has no delay_days/severity to report — this must
    # not require the caller to pass them explicitly as None.
    result = RiskAssessment(order_id="o1", order_status="delivered", is_late=False, is_at_risk=False)
    assert result.delay_days is None
    assert result.severity is None


def test_compensation_proposal_optional_fields_default_to_none_when_omitted():
    # An ineligible order has no severity/amount to report.
    result = CompensationProposal(
        order_id="o1", eligible=False, reason="on time",
        policy_doc_id="POL-COMP-001", policy_version="1.0",
    )
    assert result.severity is None
    assert result.proposed_amount is None
