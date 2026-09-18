import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.actions import list_actions, resolve_action
from app.agent.graph import AGENT_GRAPH, ROUTING_GRAPH
from app.agent.llm import stream_model
from app.agent.nodes import ABSTENTION_MESSAGE, propose_or_finalize
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
    ActionSummary,
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


def _build_chat_state(request: ChatRequest, current_user: CurrentUser) -> tuple[str, AgentState]:
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
    return conversation_id, state


def _extract_proposal(proposal_data: dict | None) -> tuple[CompensationProposal | None, str | None]:
    if proposal_data is None:
        return None, None
    proposal_fields = {k: v for k, v in proposal_data.items() if k != "action_id"}
    return CompensationProposal(**proposal_fields), proposal_data["action_id"]


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation_id, state = _build_chat_state(request, current_user)

    result = AGENT_GRAPH.invoke(state)
    append_messages(conversation_id, request.message, result["answer"])
    proposal, action_id = _extract_proposal(result["proposal"])

    return ChatResponse(
        conversation_id=conversation_id,
        answer=result["answer"],
        citations=result["evidence"],
        proposal=proposal,
        action_id=action_id,
    )


def _sse_event(event: str, data: dict | str) -> str:
    # Always JSON-encode, even plain chunk text - a raw multi-line chunk
    # (e.g. a paragraph break in the model's answer) would otherwise break
    # SSE framing, since a "data:" line can't contain a literal newline.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    conversation_id, state = _build_chat_state(request, current_user)

    def event_stream():
        try:
            routed = ROUTING_GRAPH.invoke(state)

            if routed["answer"] is not None:
                answer = routed["answer"]
                yield _sse_event("chunk", answer)
            elif routed["abstain"]:
                answer = ABSTENTION_MESSAGE
                yield _sse_event("chunk", answer)
            else:
                pieces: list[str] = []
                for delta in stream_model(routed["messages"]):
                    pieces.append(delta)
                    yield _sse_event("chunk", delta)
                answer = "".join(pieces)

            routed["answer"] = answer
            final = propose_or_finalize(routed)
            append_messages(conversation_id, request.message, answer)
            proposal, action_id = _extract_proposal(final["proposal"])

            yield _sse_event("done", {
                "conversation_id": conversation_id,
                "citations": [c.model_dump(mode="json") for c in final["evidence"]],
                "proposal": proposal.model_dump(mode="json") if proposal else None,
                "action_id": action_id,
            })
        except Exception as exc:  # noqa: BLE001 - must convert any failure into an SSE error event, never let it propagate mid-stream
            yield _sse_event("error", {"detail": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/actions", response_model=list[ActionSummary])
def read_actions(
    status: str | None = None,
    current_user: CurrentUser = Depends(require_permission("can_approve_compensation")),
):
    return list_actions(status)


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
