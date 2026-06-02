"""LangGraph nodes.

Each node mutates a shared `AgentState` (a TypedDict). Edges in graph.py
read the state to decide where to go next.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, TypedDict

from agentstack.config import settings
from agentstack.core.agent.citations import build_context_block, extract_citations
from agentstack.core.agent.prompts import ROUTER_V1, SYNTHESIZER_V1
from agentstack.core.agent.tools import web_search as run_web_search
from agentstack.core.retrieval.hybrid import HybridRetriever, RetrievedChunk
from agentstack.infra.llm import get_chat_client
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import LLM_TOKENS
from agentstack.infra.tracing import (
    INPUT_VALUE,
    OUTPUT_VALUE,
    SPAN_KIND,
    get_tracer,
    set_attrs,
    truncate,
)

logger = get_logger(__name__)


class AgentState(TypedDict, total=False):
    question: str
    collection_id: str
    top_k: int
    use_web_search: bool
    prior_turns: list[dict]
    intent: str
    retrieved: list[RetrievedChunk]
    web_results: list[dict]
    answer: str
    citations: list[dict]
    tools_used: list[str]
    prompt_tokens: int
    completion_tokens: int
    model: str
    error: str | None


_VALID_INTENTS = {"factual", "analytical", "comparison", "web", "code", "conversational"}


async def router_node(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.router") as span:
        set_attrs(span, **{SPAN_KIND: "CHAIN", INPUT_VALUE: state.get("question", "")})
        client = get_chat_client()
        prompt = ROUTER_V1.render(question=state["question"])
        resp = await client.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=8,
        )
        raw = _extract_text(resp).strip().lower()
        intent = next(
            (label for label in _VALID_INTENTS if raw.startswith(label) or raw.endswith(label)),
            "factual",
        )
        state["intent"] = intent
        _record_tokens(resp, kind="router")
        set_attrs(span, **{"agent.intent": intent, OUTPUT_VALUE: intent})
        return state


async def retrieve_node(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.retrieve") as span:
        set_attrs(span, **{SPAN_KIND: "CHAIN", INPUT_VALUE: state.get("question", "")})
        retriever = HybridRetriever()
        chunks = await retriever.retrieve(
            state["collection_id"],
            state["question"],
            top_k=int(state.get("top_k", 5)),
        )
        state["retrieved"] = chunks
        state.setdefault("tools_used", []).append("retrieve")
        set_attrs(span, **{"agent.retrieved_n": len(chunks)})
        return state


async def web_search_node(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.web_search") as span:
        set_attrs(
            span,
            **{
                SPAN_KIND: "TOOL",
                "tool.name": "tavily.web_search",
                INPUT_VALUE: state.get("question", ""),
            },
        )
        if not state.get("use_web_search", True) or not settings.tavily_api_key:
            state["web_results"] = []
            set_attrs(span, **{"agent.web_results_n": 0, "tool.skipped": True})
            return state
        try:
            result = run_web_search(state["question"], max_results=5)
            state["web_results"] = result.get("results", [])
        except Exception as e:
            logger.warning("web_search failed", error=str(e))
            state["web_results"] = []
            span.record_exception(e)
        state.setdefault("tools_used", []).append("web_search")
        set_attrs(span, **{"agent.web_results_n": len(state["web_results"])})
        return state


async def code_exec_node(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.code_exec") as span:
        set_attrs(span, **{SPAN_KIND: "TOOL", "tool.name": "code_exec", "tool.disabled": True})
        state.setdefault("tools_used", []).append("code_exec")
        state["error"] = "code_exec is disabled in this build."
        return state


def build_synthesis_messages(state: AgentState) -> list[dict]:
    """Render the LLM input for synthesis. Shared between non-streaming and SSE paths."""
    chunks: list[RetrievedChunk] = list(state.get("retrieved") or [])
    web = state.get("web_results") or []

    if web:
        web_block = "\n\n".join(
            f"[w{i + 1}] {r.get('snippet') or ''} (source: {r.get('url')})"
            for i, r in enumerate(web)
        )
    else:
        web_block = ""

    chunk_block = build_context_block(chunks)
    context = chunk_block if not web_block else f"{chunk_block}\n\n{web_block}"

    messages: list[dict] = []
    for turn in state.get("prior_turns", []) or []:
        if isinstance(turn, dict) and "role" in turn and "content" in turn:
            messages.append(turn)

    messages.append(
        {
            "role": "user",
            "content": SYNTHESIZER_V1.render(question=state["question"], context=context),
        }
    )
    return messages


async def synthesize_node(state: AgentState) -> AgentState:
    tracer = get_tracer()
    with tracer.start_as_current_span("agent.synthesize") as span:
        chunks: list[RetrievedChunk] = list(state.get("retrieved") or [])
        messages = build_synthesis_messages(state)
        set_attrs(
            span,
            **{
                SPAN_KIND: "CHAIN",
                INPUT_VALUE: truncate(messages),
                "agent.context_chunks": len(chunks),
            },
        )

        client = get_chat_client()
        resp = await client.complete(messages=messages, temperature=0.2, max_tokens=800)
        answer = _extract_text(resp).strip()
        set_attrs(span, **{OUTPUT_VALUE: truncate(answer)})

    state["answer"] = answer
    citations = extract_citations(answer, chunks)
    state["citations"] = [c.model_dump(mode="json") for c in citations]
    state["model"] = client.model

    _record_tokens(resp, kind="synthesize")
    state["prompt_tokens"] = state.get("prompt_tokens", 0) + _get(resp, "prompt_tokens")
    state["completion_tokens"] = state.get("completion_tokens", 0) + _get(resp, "completion_tokens")
    return state


async def reflect_node(state: AgentState) -> AgentState:
    return state


def route_after_router(state: AgentState) -> str:
    intent = state.get("intent", "factual")
    if intent == "web":
        return "web_search"
    if intent == "code":
        return "code_exec"
    return "retrieve"


def needs_web_fallback(state: AgentState) -> str:
    if not state.get("retrieved") and state.get("use_web_search", True):
        return "web_search"
    return "synthesize"


def _extract_text(resp: dict[str, Any]) -> str:
    try:
        return resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


def _get(resp: dict[str, Any], field: str) -> int:
    usage = (resp or {}).get("usage") or {}
    return int(usage.get(field, 0) or 0)


def _record_tokens(resp: dict[str, Any], *, kind: str) -> None:
    usage = (resp or {}).get("usage") or {}
    model = (resp or {}).get("model") or settings.groq_chat_model
    for label, field in (("prompt", "prompt_tokens"), ("completion", "completion_tokens")):
        n = int(usage.get(field, 0) or 0)
        if n:
            LLM_TOKENS.labels(provider="groq", model=model, kind=label).inc(n)


__all__ = [
    "AgentState",
    "build_synthesis_messages",
    "code_exec_node",
    "needs_web_fallback",
    "reflect_node",
    "retrieve_node",
    "route_after_router",
    "router_node",
    "synthesize_node",
    "web_search_node",
]


def _as_dict(obj: Any) -> dict:
    if is_dataclass(obj):
        return asdict(obj)
    return dict(obj) if isinstance(obj, dict) else {"value": obj}
