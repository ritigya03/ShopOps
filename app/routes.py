import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.auth import CurrentUser
from app.db import get_engine
from app.guardrails import InsufficientEvidenceError, assert_evidence_present, require_permission
from app.schemas import CompensationProposal, OrderTimeline, PolicyEvidence, RiskAssessment, SellerMetrics
from app.tools import calculate_compensation, estimate_delivery_risk, get_order, get_seller_metrics, search_policy

router = APIRouter()


def _log_audit(user: CurrentUser, tool_name: str, outcome: str) -> None:
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


@router.get("/orders/{order_id}", response_model=OrderTimeline)
def read_order(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_order")),
):
    result = get_order(order_id)
    _log_audit(current_user, "get_order", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/sellers/{seller_id}/metrics", response_model=SellerMetrics)
def read_seller_metrics(
    seller_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_seller_metrics")),
):
    result = get_seller_metrics(seller_id)
    _log_audit(current_user, "get_seller_metrics", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Seller not found")
    return result


@router.get("/policy/search", response_model=list[PolicyEvidence])
def read_policy_search(
    query: str,
    domain: str | None = None,
    current_user: CurrentUser = Depends(require_permission("can_search_policy")),
):
    results = search_policy(query, domain=domain)
    try:
        results = assert_evidence_present(results)
        _log_audit(current_user, "search_policy", "success")
    except InsufficientEvidenceError:
        _log_audit(current_user, "search_policy", "insufficient_evidence")
        raise HTTPException(status_code=404, detail="No sufficiently relevant policy passage found")
    return results


@router.get("/orders/{order_id}/risk", response_model=RiskAssessment)
def read_delivery_risk(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_delivery_risk")),
):
    result = estimate_delivery_risk(order_id)
    _log_audit(current_user, "estimate_delivery_risk", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/orders/{order_id}/compensation", response_model=CompensationProposal)
def read_compensation_proposal(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_propose_compensation")),
):
    result = calculate_compensation(order_id)
    _log_audit(current_user, "calculate_compensation", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order or active policy not found")
    return result
