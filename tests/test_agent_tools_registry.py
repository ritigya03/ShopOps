from app.agent.tools_registry import TOOL_DISPATCH, TOOLS
from app.guardrails import PERMISSIONS
from app.tools import (
    calculate_compensation,
    estimate_delivery_risk,
    get_order,
    get_seller_metrics,
    search_policy,
)


def test_every_tool_schema_has_a_dispatch_entry():
    schema_names = {t["function"]["name"] for t in TOOLS}
    assert schema_names == set(TOOL_DISPATCH.keys())


def test_every_dispatch_permission_is_granted_to_some_role():
    all_permissions = set().union(*PERMISSIONS.values())
    for tool_name, (_, permission) in TOOL_DISPATCH.items():
        assert permission in all_permissions, f"{tool_name}'s permission {permission!r} is granted to no role"


def test_dispatch_functions_match_the_real_tool_functions():
    assert TOOL_DISPATCH["get_order"][0] is get_order
    assert TOOL_DISPATCH["get_seller_metrics"][0] is get_seller_metrics
    assert TOOL_DISPATCH["search_policy"][0] is search_policy
    assert TOOL_DISPATCH["estimate_delivery_risk"][0] is estimate_delivery_risk
    assert TOOL_DISPATCH["calculate_compensation"][0] is calculate_compensation


def test_tool_schemas_have_required_openai_fields():
    for tool in TOOLS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert fn["name"] and fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert "required" in fn["parameters"]
