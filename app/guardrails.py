from fastapi import Depends, HTTPException

from app.audit import log_audit
from app.auth import CurrentUser, get_current_user
from app.schemas import PolicyEvidence

PERMISSIONS: dict[str, set[str]] = {
    "Viewer": {"can_view_order", "can_search_policy"},
    "SupportAgent": {
        "can_view_order", "can_search_policy",
        "can_view_delivery_risk", "can_propose_compensation",
    },
    "OperationsManager": {
        "can_view_order", "can_search_policy", "can_view_delivery_risk",
        "can_propose_compensation", "can_view_seller_metrics", "can_approve_compensation",
        "can_view_audit_log",
    },
}


class InsufficientEvidenceError(Exception):
    pass


def require_permission(permission: str):
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if permission not in PERMISSIONS.get(current_user.role, set()):
            log_audit(current_user, permission, "denied")
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user.role}' lacks permission '{permission}'",
            )
        return current_user
    return dependency


def assert_evidence_present(evidence: list[PolicyEvidence], min_score: float = 0.3) -> list[PolicyEvidence]:
    strong = [e for e in evidence if e.score >= min_score]
    if not strong:
        raise InsufficientEvidenceError("No policy passage met the minimum relevance score")
    return strong
