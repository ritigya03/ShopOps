from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.audit import log_audit
from app.auth import CurrentUser

pytestmark = pytest.mark.integration


def test_log_audit_persists_citations_and_policy_version(engine):
    user = CurrentUser(sub="test-sub-audit-1", email="t@example.com", role="Viewer")
    before = datetime.now(timezone.utc)
    citations = [{"doc_id": "POL-COMP-001", "version": "1.0", "section": "2", "excerpt": "text", "score": 0.9}]

    log_audit(user, "calculate_compensation", "success", citations=citations, policy_version="1.0")

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT citations, policy_version FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND user_id = :user_id
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before, "user_id": "test-sub-audit-1"}).mappings().first()

    assert row is not None
    assert row["policy_version"] == "1.0"
    assert row["citations"][0]["doc_id"] == "POL-COMP-001"


def test_log_audit_without_citations_still_works(engine):
    user = CurrentUser(sub="test-sub-audit-2", email="t@example.com", role="Viewer")
    before = datetime.now(timezone.utc)

    log_audit(user, "get_order", "success")

    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT citations, policy_version FROM shopops_ops.audit_events
            WHERE occurred_at > :before AND user_id = :user_id
            ORDER BY occurred_at DESC LIMIT 1
        """), {"before": before, "user_id": "test-sub-audit-2"}).mappings().first()

    assert row is not None
    assert row["citations"] is None
    assert row["policy_version"] is None
