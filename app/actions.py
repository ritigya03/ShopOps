import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text

from app.audit import log_audit
from app.auth import CurrentUser
from app.db import get_engine
from app.schemas import ActionReceipt, ActionSummary
from app.tools import calculate_compensation


def _payload_hash(order_id: str, amount, policy_version: str) -> str:
    return hashlib.sha256(f"{order_id}:{amount}:{policy_version}".encode()).hexdigest()


def resolve_action(action_id: str, user: CurrentUser, approve: bool) -> ActionReceipt:
    with get_engine().begin() as conn:
        row = conn.execute(text("""
            SELECT action_id, order_id, status, approved_by, policy_version, payload_hash, approved_amount,
                   (expires_at IS NOT NULL AND expires_at < now()) AS is_expired
            FROM shopops_ops.action_requests WHERE action_id = :id
        """), {"id": action_id}).mappings().first()

        if row is None:
            raise HTTPException(status_code=404, detail="Action not found")

        if row["status"] == "SUCCEEDED":
            return ActionReceipt(
                action_id=action_id, status="SUCCEEDED", approved_by=row["approved_by"],
                order_id=row["order_id"], proposed_amount=row["approved_amount"],
                occurred_at=datetime.now(timezone.utc),
            )

        if row["status"] != "PROPOSED":
            raise HTTPException(status_code=409, detail=f"Action is '{row['status']}', not 'PROPOSED'")

        if row["is_expired"]:
            raise HTTPException(status_code=409, detail="Proposal has expired; request a fresh one")

        approved_amount = None
        if approve:
            fresh = calculate_compensation(row["order_id"], row["policy_version"])
            if fresh is None or not fresh.eligible:
                raise HTTPException(
                    status_code=409, detail="Order is no longer eligible for compensation; request a fresh proposal"
                )
            fresh_hash = _payload_hash(row["order_id"], fresh.proposed_amount, fresh.policy_version)
            if fresh_hash != row["payload_hash"]:
                raise HTTPException(
                    status_code=409, detail="Proposal is stale (order/policy data changed); request a fresh one"
                )
            approved_amount = fresh.proposed_amount

        new_status = "SUCCEEDED" if approve else "REJECTED"
        conn.execute(text("""
            UPDATE shopops_ops.action_requests
            SET status = :status, approved_by = :approved_by, approved_amount = :amount, updated_at = now()
            WHERE action_id = :id
        """), {"status": new_status, "approved_by": user.sub, "amount": approved_amount, "id": action_id})

    log_audit(user, "calculate_compensation", "approved" if approve else "rejected", policy_version=row["policy_version"])

    return ActionReceipt(
        action_id=action_id, status=new_status, approved_by=user.sub,
        order_id=row["order_id"], proposed_amount=approved_amount,
        occurred_at=datetime.now(timezone.utc),
    )


def list_actions(status: str | None) -> list[ActionSummary]:
    query = """
        SELECT action_id, order_id, status, requested_by, approved_by, policy_version,
               expires_at, approved_amount, created_at,
               (expires_at IS NOT NULL AND expires_at < now()) AS is_expired
        FROM shopops_ops.action_requests
    """
    params: dict = {}
    if status:
        query += " WHERE status = :status"
        params["status"] = status
    query += " ORDER BY created_at DESC"

    with get_engine().connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    summaries = []
    for row in rows:
        proposal = calculate_compensation(row["order_id"], row["policy_version"])
        amount = row["approved_amount"] if row["status"] == "SUCCEEDED" else (proposal.proposed_amount if proposal else None)
        summaries.append(ActionSummary(
            action_id=str(row["action_id"]), order_id=row["order_id"], status=row["status"],
            requested_by=row["requested_by"], approved_by=row["approved_by"],
            policy_version=row["policy_version"], expires_at=row["expires_at"],
            is_expired=row["is_expired"], created_at=row["created_at"],
            proposed_amount=amount,
            severity=proposal.severity if proposal else None,
            reason=proposal.reason if proposal else None,
        ))
    return summaries
