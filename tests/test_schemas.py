from decimal import Decimal

from app.schemas import PolicyEvidence


def test_policy_evidence_requires_score_between_0_and_1():
    evidence = PolicyEvidence(
        doc_id="POL-COMP-001", version="1.0", section="3. Compensation tiers",
        excerpt="...", score=0.53,
    )
    assert evidence.score == 0.53
