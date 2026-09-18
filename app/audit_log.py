from sqlalchemy import text

from app.db import get_engine
from app.schemas import AuditEventSummary


def list_audit_events(limit: int) -> list[AuditEventSummary]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT event_id, occurred_at, user_id, role_snapshot, tool_name, outcome, policy_version
            FROM shopops_ops.audit_events
            ORDER BY occurred_at DESC
            LIMIT :limit
        """), {"limit": limit}).mappings().all()
    return [AuditEventSummary(**{**row, "event_id": str(row["event_id"])}) for row in rows]
