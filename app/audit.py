import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.auth import CurrentUser
from app.db import get_engine


def log_audit(user: CurrentUser, tool_name: str, outcome: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO shopops_ops.audit_events
                (event_id, occurred_at, request_id, user_id, role_snapshot, tool_name, outcome)
            VALUES (:event_id, :occurred_at, :request_id, :user_id, :role, :tool_name, :outcome)
        """), {
            "event_id": str(uuid.uuid4()), "occurred_at": datetime.now(timezone.utc),
            "request_id": str(uuid.uuid4()), "user_id": user.sub, "role": user.role,
            "tool_name": tool_name, "outcome": outcome,
        })
