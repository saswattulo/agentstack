# ADR 003 — Agent framework: LangGraph

- **Status:** Accepted
- **Date:** 2026-05-30

## Context

The query pipeline is not a fixed chain. It branches:

- Factual / analytical questions go straight to retrieval.
- "What happened in the news this week" should route to web search instead.
- Empty retrieval results should fall back to web search.
- Low-confidence synthesis should loop back through critique.

Options:

1. **Plain Python** — write the state machine by hand. Most control, most boilerplate, no tracing affordances.
2. **LangChain Chains / Agents (LCEL)** — works for linear pipelines; the agent abstraction is opinionated and harder to debug.
3. **LangGraph** — stateful DAG with conditional edges, first-class for branching agents, integrates with the LangChain trace ecosystem.

## Decision

Use **LangGraph** for the query orchestration. Keep ingestion in plain Python — it doesn't branch.

## Rationale

- The branching pattern (router → retrieve | web | code → synthesize → reflect) maps cleanly onto LangGraph's `add_conditional_edges`. Writing this in plain Python is doable but obscures the topology; LangGraph makes it visible in code and traceable via Phoenix.
- LangGraph state is a `TypedDict`. We do not need its checkpointing features yet, but they exist if we add long-running agents later.
- Streaming token output is supported natively, which we need for `POST /query/stream`.

## Consequences

- Added dependency on `langgraph` + `langchain-core`. Their versions move quickly.
- The agent must be aware of the LangGraph state contract (`AgentState`). Nodes are async functions returning the state.

## Revisit when

- We need a long-running agent with checkpointed state — LangGraph still wins, but check the persistence API.
- LangGraph introduces a breaking change we cannot absorb. At that point the manual rewrite is small because `nodes.py` is decoupled from the framework.
