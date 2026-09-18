import hashlib
import json
import logging
import time
import uuid

from sqlalchemy import text

from app.agent.llm import call_model
from app.agent.state import AgentState
from app.agent.tools_registry import TOOL_DISPATCH, TOOLS
from app.audit import log_audit
from app.db import get_engine
from app.guardrails import (
    PERMISSIONS,
    InsufficientEvidenceError,
    assert_evidence_present,
)

logger = logging.getLogger("shopops.tools")


def route_or_tools(state: AgentState) -> AgentState:
    response = call_model(state["messages"], tools=TOOLS)
    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []

    assistant_entry: dict = {"role": "assistant", "content": message.content or ""}
    pending: list[dict] = []
    if tool_calls:
        assistant_entry["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls
        ]
        pending = [
            {"id": tc.id, "name": tc.function.name, "args": json.loads(tc.function.arguments)}
            for tc in tool_calls
        ]

    state["messages"] = [*state["messages"], assistant_entry]
    state["pending_tool_calls"] = pending
    if not pending:
        state["answer"] = message.content or ""
    return state


def execute_tools(state: AgentState) -> AgentState:
    user = state["user"]
    tool_results = list(state["tool_results"])
    tool_messages: list[dict] = []
    new_evidence = list(state["evidence"])

    for call in state["pending_tool_calls"]:
        name, args = call["name"], call["args"]
        fn, permission = TOOL_DISPATCH[name]
        start = time.monotonic()

        if permission not in PERMISSIONS.get(user.role, set()):
            outcome = "denied"
            log_audit(user, name, outcome)
            tool_results.append({"tool_name": name, "args": args, "result": None, "error": "permission_denied"})
            content = f"Permission denied: role '{user.role}' cannot use tool '{name}'."
        else:
            try:
                result = fn(**args)
            except Exception:
                # Re-raising exits the loop, so the trailing logger.info() for
                # this iteration never runs — no double-logging.
                duration_ms = (time.monotonic() - start) * 1000
                # G201 suppressed: kept as .error(..., exc_info=True) so this
                # line is visibly the same shape as the success/denied log.
                logger.error(  # noqa: G201
                    "tool_call",
                    extra={
                        "tool_name": name,
                        "outcome": "error",
                        "duration_ms": duration_ms,
                        "permission": permission,
                    },
                    exc_info=True,
                )
                raise
            outcome = "success" if result is not None else "not_found"
            log_audit(user, name, outcome)
            if result is None:
                tool_results.append({"tool_name": name, "args": args, "result": None, "error": "not_found"})
                content = f"No data found for {name}({args})."
            elif isinstance(result, list):
                dumped = [item.model_dump(mode="json") for item in result]
                tool_results.append({"tool_name": name, "args": args, "result": dumped, "error": None})
                content = json.dumps(dumped)
                if name == "search_policy":
                    new_evidence.extend(result)
            else:
                dumped = result.model_dump(mode="json")
                tool_results.append({"tool_name": name, "args": args, "result": dumped, "error": None})
                content = json.dumps(dumped)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "tool_call",
            extra={"tool_name": name, "outcome": outcome, "duration_ms": duration_ms, "permission": permission},
        )
        tool_messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": content})

    state["tool_results"] = tool_results
    state["evidence"] = new_evidence
    state["messages"] = [*state["messages"], *tool_messages]
    state["loop_count"] = state["loop_count"] + 1
    state["pending_tool_calls"] = []
    return state


def route_after_routing(state: AgentState) -> str:
    return "execute_tools" if state["pending_tool_calls"] else "validate_evidence"


def route_after_tools(state: AgentState) -> str:
    return "validate_evidence" if state["loop_count"] >= 2 else "route_or_tools"


def validate_evidence(state: AgentState) -> AgentState:
    if not state["evidence"]:
        state["abstain"] = False
        return state
    try:
        state["evidence"] = assert_evidence_present(state["evidence"])
        state["abstain"] = False
    except InsufficientEvidenceError:
        state["abstain"] = True
    return state


ABSTENTION_MESSAGE = (
    "I don't have a sufficiently relevant policy passage to answer that with confidence. "
    "Please have this reviewed manually or rephrase the question."
)


def synthesize(state: AgentState) -> AgentState:
    if state["answer"] is not None:
        return state  # model already produced a final answer with no tools needed

    if state["abstain"]:
        state["answer"] = ABSTENTION_MESSAGE
        return state

    response = call_model(state["messages"])
    state["answer"] = response.choices[0].message.content or ""
    return state


def _find_eligible_compensation(state: AgentState) -> dict | None:
    for tr in state["tool_results"]:
        if tr["tool_name"] == "calculate_compensation" and tr["result"] and tr["result"].get("eligible"):
            return tr["result"]
    return None


def propose_or_finalize(state: AgentState) -> AgentState:
    user = state["user"]
    proposal_data = _find_eligible_compensation(state)

    if (
        proposal_data is None
        or "can_propose_compensation" not in PERMISSIONS.get(user.role, set())
        or state["abstain"]
    ):
        state["proposal"] = None
        return state

    order_id = proposal_data["order_id"]
    amount = str(proposal_data["proposed_amount"])
    policy_version = proposal_data["policy_version"]
    payload_hash = hashlib.sha256(f"{order_id}:{amount}:{policy_version}".encode()).hexdigest()
    idempotency_key = str(uuid.uuid4())

    with get_engine().begin() as conn:
        row = conn.execute(text("""
            INSERT INTO shopops_ops.action_requests
                (action_type, order_id, payload_hash, status, requested_by, idempotency_key, policy_version, expires_at)
            VALUES ('compensation_proposal', :order_id, :payload_hash, 'PROPOSED', :requested_by,
                    :idempotency_key, :policy_version, now() + interval '24 hours')
            RETURNING action_id
        """), {
            "order_id": order_id, "payload_hash": payload_hash, "requested_by": user.sub,
            "idempotency_key": idempotency_key, "policy_version": policy_version,
        }).mappings().first()

    state["proposal"] = {**proposal_data, "action_id": str(row["action_id"])}
    return state
