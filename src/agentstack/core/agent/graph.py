"""LangGraph state machine assembly.

Week 2 — wire the nodes from `nodes.py` into a graph with conditional edges.
The exported `compiled_graph` is what `api/routes/query.py` will invoke once
the stub is replaced.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agentstack.core.agent.nodes import (
    AgentState,
    code_exec_node,
    needs_web_fallback,
    reflect_node,
    retrieve_node,
    route_after_router,
    router_node,
    synthesize_node,
    web_search_node,
)


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("code_exec", code_exec_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("reflect", reflect_node)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieve": "retrieve", "web_search": "web_search", "code_exec": "code_exec"},
    )
    graph.add_conditional_edges(
        "retrieve",
        needs_web_fallback,
        {"web_search": "web_search", "synthesize": "synthesize"},
    )
    graph.add_edge("web_search", "synthesize")
    graph.add_edge("code_exec", "synthesize")
    graph.add_edge("synthesize", "reflect")
    graph.add_edge("reflect", END)

    return graph.compile()


compiled_graph = None


def get_compiled_graph():
    global compiled_graph
    if compiled_graph is None:
        compiled_graph = build_graph()
    return compiled_graph
