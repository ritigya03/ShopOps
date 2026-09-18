from fastapi import APIRouter, Depends, HTTPException

from app.actions import resolve_action
from app.agent.graph import AGENT_GRAPH
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.audit import log_audit
from app.auth import CurrentUser, get_current_user
from app.conversations import (
    append_messages,
    create_conversation,
    get_conversation_owner,
    load_recent_messages,
)
from app.guardrails import (
    InsufficientEvidenceError,
    assert_evidence_present,
    require_permission,
)
from app.schemas import (
    ActionReceipt,
    ChatRequest,
    ChatResponse,
    CompensationProposal,
    OrderTimeline,
    PolicyEvidence,
    RiskAssessment,
    SellerMetrics,
)
from app.tools import (
    calculate_compensation,
    estimate_delivery_risk,
    get_order,
    get_seller_metrics,
    search_policy,
)

router = APIRouter()


@router.get("/orders/{order_id}", response_model=OrderTimeline)
def read_order(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_order")),
):
    result = get_order(order_id)
    log_audit(current_user, "get_order", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/sellers/{seller_id}/metrics", response_model=SellerMetrics)
def read_seller_metrics(
    seller_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_seller_metrics")),
):
    result = get_seller_metrics(seller_id)
    log_audit(current_user, "get_seller_metrics", "success" if result else "not_found")
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
        log_audit(current_user, "search_policy", "success")
    except InsufficientEvidenceError:
        log_audit(current_user, "search_policy", "insufficient_evidence")
        raise HTTPException(status_code=404, detail="No sufficiently relevant policy passage found")
    return results


@router.get("/orders/{order_id}/risk", response_model=RiskAssessment)
def read_delivery_risk(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_view_delivery_risk")),
):
    result = estimate_delivery_risk(order_id)
    log_audit(current_user, "estimate_delivery_risk", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("/orders/{order_id}/compensation", response_model=CompensationProposal)
def read_compensation_proposal(
    order_id: str,
    current_user: CurrentUser = Depends(require_permission("can_propose_compensation")),
):
    result = calculate_compensation(order_id)
    log_audit(current_user, "calculate_compensation", "success" if result else "not_found")
    if result is None:
        raise HTTPException(status_code=404, detail="Order or active policy not found")
    return result


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    if request.conversation_id:
        owner = get_conversation_owner(request.conversation_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if owner != current_user.sub:
            raise HTTPException(status_code=403, detail="Conversation belongs to another user")
        conversation_id = request.conversation_id
        history = load_recent_messages(conversation_id)
    else:
        conversation_id = create_conversation(current_user.sub)
        history = []

    state: AgentState = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": request.message},
        ],
        "user": current_user,
        "pending_tool_calls": [],
        "tool_results": [],
        "evidence": [],
        "abstain": False,
        "loop_count": 0,
        "answer": None,
        "proposal": None,
    }

    result = AGENT_GRAPH.invoke(state)
    append_messages(conversation_id, request.message, result["answer"])

    proposal = None
    action_id = None
    if result["proposal"] is not None:
        proposal_fields = {k: v for k, v in result["proposal"].items() if k != "action_id"}
        proposal = CompensationProposal(**proposal_fields)
        action_id = result["proposal"]["action_id"]

    return ChatResponse(
        conversation_id=conversation_id,
        answer=result["answer"],
        citations=result["evidence"],
        proposal=proposal,
        action_id=action_id,
    )


@router.post("/actions/{action_id}/approve", response_model=ActionReceipt)
def approve_action(
    action_id: str,
    current_user: CurrentUser = Depends(require_permission("can_approve_compensation")),
):
    return resolve_action(action_id, current_user, approve=True)


@router.post("/actions/{action_id}/reject", response_model=ActionReceipt)
def reject_action(
    action_id: str,
    current_user: CurrentUser = Depends(require_permission("can_approve_compensation")),
):
    return resolve_action(action_id, current_user, approve=False)
