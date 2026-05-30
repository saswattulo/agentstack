"""LangGraph nodes — Week 2 work.

Each node mutates a shared `AgentState` (a TypedDict). Edges in graph.py
read the state to decide where to go next.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    collection_id: str
    intent: str
    retrieved: list[dict]
    web_results: list[dict]
    answer: str
    citations: list[dict]
    tools_used: list[str]
    error: str | None


async def router_node(state: AgentState) -> AgentState:
    """Classify intent, populate state["intent"]."""
    # TODO(week-2): call llm with prompts.ROUTER_V1
    state["intent"] = "factual"
    return state


async def retrieve_node(state: AgentState) -> AgentState:
    """Hybrid retrieval. Populate state["retrieved"]."""
    # TODO(week-2): HybridRetriever().retrieve(...)
    state["retrieved"] = []
    state.setdefault("tools_used", []).append("retrieve")
    return state


async def web_search_node(state: AgentState) -> AgentState:
    """Fallback to Tavily. Populate state["web_results"]."""
    # TODO(week-2): tools.web_search(state["question"])
    state["web_results"] = []
    state.setdefault("tools_used", []).append("web_search")
    return state


async def code_exec_node(state: AgentState) -> AgentState:
    """Stub today — see CLAUDE.md."""
    state.setdefault("tools_used", []).append("code_exec")
    state["error"] = "code_exec is disabled in this build."
    return state


async def synthesize_node(state: AgentState) -> AgentState:
    """Generate answer with citations. Populate state["answer"] and state["citations"]."""
    # TODO(week-2): call llm with prompts.SYNTHESIZER_V1, parse citations
    state["answer"] = "Synthesis not yet implemented."
    state["citations"] = []
    return state


async def reflect_node(state: AgentState) -> AgentState:
    """Self-critique, optionally request retry. Stretch."""
    return state


def route_after_router(state: AgentState) -> str:
    intent = state.get("intent", "factual")
    if intent == "web":
        return "web_search"
    if intent == "code":
        return "code_exec"
    return "retrieve"


def needs_web_fallback(state: AgentState) -> str:
    if not state.get("retrieved"):
        return "web_search"
    return "synthesize"


__all__ = [
    "AgentState",
    "code_exec_node",
    "needs_web_fallback",
    "reflect_node",
    "retrieve_node",
    "route_after_router",
    "router_node",
    "synthesize_node",
    "web_search_node",
]
