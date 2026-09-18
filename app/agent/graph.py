from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    execute_tools,
    propose_or_finalize,
    route_after_routing,
    route_after_tools,
    route_or_tools,
    synthesize,
    validate_evidence,
)
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route_or_tools", route_or_tools)
    graph.add_node("execute_tools", execute_tools)
    graph.add_node("validate_evidence", validate_evidence)
    graph.add_node("synthesize", synthesize)
    graph.add_node("propose_or_finalize", propose_or_finalize)

    graph.set_entry_point("route_or_tools")
    graph.add_conditional_edges("route_or_tools", route_after_routing, {
        "execute_tools": "execute_tools", "validate_evidence": "validate_evidence",
    })
    graph.add_conditional_edges("execute_tools", route_after_tools, {
        "route_or_tools": "route_or_tools", "validate_evidence": "validate_evidence",
    })
    graph.add_edge("validate_evidence", "synthesize")
    graph.add_edge("synthesize", "propose_or_finalize")
    graph.add_edge("propose_or_finalize", END)

    return graph.compile()


AGENT_GRAPH = build_graph()
