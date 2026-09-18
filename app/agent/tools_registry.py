from typing import Callable

from app.tools import (
    calculate_compensation,
    estimate_delivery_risk,
    get_order,
    get_seller_metrics,
    search_policy,
)

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Look up an order's status, purchase/delivery dates, value, and seller count by order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID to look up."},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_seller_metrics",
            "description": "Look up a seller's order count, late-delivery rate, and average review score by seller ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seller_id": {"type": "string", "description": "The seller ID to look up."},
                },
                "required": ["seller_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": (
                "Search ShopOps policy documents for passages relevant to a question, e.g. "
                "compensation eligibility or refund rules. Returns cited passages with a relevance score."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The natural-language question to search policy for."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_delivery_risk",
            "description": "Assess whether an order was delivered late and how severe the delay was, by order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID to assess."},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_compensation",
            "description": (
                "Calculate whether an order is eligible for delivery-delay compensation and, if so, "
                "the proposed amount under the active policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order ID to evaluate."},
                },
                "required": ["order_id"],
            },
        },
    },
]

TOOL_DISPATCH: dict[str, tuple[Callable[..., object], str]] = {
    "get_order": (get_order, "can_view_order"),
    "get_seller_metrics": (get_seller_metrics, "can_view_seller_metrics"),
    "search_policy": (search_policy, "can_search_policy"),
    "estimate_delivery_risk": (estimate_delivery_risk, "can_view_delivery_risk"),
    "calculate_compensation": (calculate_compensation, "can_propose_compensation"),
}
