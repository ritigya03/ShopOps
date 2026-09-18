from typing import TypedDict

from app.auth import CurrentUser
from app.schemas import PolicyEvidence


class PendingToolCall(TypedDict):
    id: str
    name: str
    args: dict


class ToolResult(TypedDict):
    tool_name: str
    args: dict
    result: dict | list | None
    error: str | None


class AgentState(TypedDict):
    messages: list[dict]
    user: CurrentUser
    pending_tool_calls: list[PendingToolCall]
    tool_results: list[ToolResult]
    evidence: list[PolicyEvidence]
    abstain: bool
    loop_count: int
    answer: str | None
    proposal: dict | None
