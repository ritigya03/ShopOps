from unittest.mock import Mock, patch

from app.agent.nodes import execute_tools
from app.auth import CurrentUser


def _state(pending_tool_calls, role="OperationsManager"):
    return {
        "user": CurrentUser(sub="u1", email="u1@example.com", role=role),
        "tool_results": [],
        "evidence": [],
        "messages": [],
        "pending_tool_calls": pending_tool_calls,
        "loop_count": 0,
    }


def test_execute_tools_logs_successful_dispatch(caplog):
    fake_fn = Mock(return_value=None)
    with (
        patch.dict("app.agent.nodes.TOOL_DISPATCH", {"get_order": (fake_fn, "can_view_order")}),
        patch("app.agent.nodes.log_audit"),
        caplog.at_level("INFO", logger="shopops.tools"),
    ):
        execute_tools(_state([{"id": "call1", "name": "get_order", "args": {"order_id": "x"}}]))

    record = next(r for r in caplog.records if r.name == "shopops.tools")
    assert record.tool_name == "get_order"
    assert record.outcome == "not_found"
    assert record.permission == "can_view_order"
    assert isinstance(record.duration_ms, float)


def test_execute_tools_logs_permission_denied(caplog):
    fake_fn = Mock(return_value=None)
    with (
        patch.dict("app.agent.nodes.TOOL_DISPATCH", {"get_seller_metrics": (fake_fn, "can_view_seller_metrics")}),
        patch("app.agent.nodes.log_audit"),
        caplog.at_level("INFO", logger="shopops.tools"),
    ):
        execute_tools(_state(
            [{"id": "call1", "name": "get_seller_metrics", "args": {"seller_id": "s1"}}],
            role="Viewer",
        ))

    record = next(r for r in caplog.records if r.name == "shopops.tools")
    assert record.outcome == "denied"
    fake_fn.assert_not_called()
