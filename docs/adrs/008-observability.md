# ADR 008 — Observability: Phoenix-backed OTel tracing, raw API instead of Langchain

- **Status:** Accepted
- **Date:** 2026-06-02

## Context

By the end of Week 2 we had Phoenix running in Compose with an OTLP receiver, and `infra/tracing.py` registering a `TracerProvider` — but no spans ever left the application. The agent path (router → retrieve → synthesize → LLM calls) was a black box from an outside-the-API perspective. Latency is logged, but causality across nodes wasn't.

Week 3 needs the trace tree visible end-to-end: every LLM call, every retriever invocation, every agent node, every top-level query, with enough attributes that someone looking at a slow query can tell *where* the time went and *what* the LLM saw.

We had two implementation choices:

1. **Langchain auto-instrumentation via `openinference-instrumentation-langchain`** — our `langchain-core` dep would emit spans automatically if we wrapped Groq through a `BaseChatModel` adapter.
2. **Manual spans via raw `opentelemetry-api`** — explicit `with tracer.start_as_current_span(...)` blocks at each instrumentation point, attribute keys following OpenInference conventions.

## Decision

**Manual spans, raw OTel API, OpenInference attribute keys.**

- `infra/tracing.py` exposes `get_tracer()` and a `set_attrs(span, **attrs)` helper that filters `None`, stringifies non-primitives, and truncates strings/JSON to 2000 chars.
- Centralized attribute key constants (`SPAN_KIND`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_PROMPT_TOKENS`, `LLM_COMPLETION_TOKENS`, `INPUT_VALUE`, `OUTPUT_VALUE`, `RETRIEVAL_QUERY`, `SESSION_ID`, `USER_ID`).
- Instrumentation points:
  - `infra/llm.py` — `llm.complete` and `llm.stream` spans (kind=LLM). Capture prompt/completion/total token counts and truncated input/output.
  - `core/retrieval/hybrid.py` — `retrieval.hybrid` span (kind=RETRIEVER) with query, top_k, dense_n, sparse_n, fused_n, reranker flag, and per-document `retrieval.documents.N.document.{id,score,content}`.
  - `core/agent/nodes.py` — one span per node (`agent.router`, `agent.retrieve`, `agent.web_search`, `agent.code_exec`, `agent.synthesize`) with kind=CHAIN or kind=TOOL where appropriate.
  - `services/query_service.py` — top-level `query` span (kind=AGENT) carrying `session.id` (conversation), `user.id`, `query.id`, `query.cache_hit`, `query.intent`, `query.latency_ms`, plus the canonical input/output values.

## Rationale

- **Why raw OTel over Langchain auto-instrumentation:** our chat client calls Groq directly via `AsyncGroq`, not through `langchain_core.language_models.BaseChatModel`. The auto-instrumentation hook is the LangChain runnable boundary; without wrapping our client in a `BaseChatModel` subclass, the spans wouldn't fire. The wrapper would be 50+ lines of glue for no functional benefit — we'd lose direct control of token streaming. Manual spans took ~80 lines total and we own every attribute that lands in Phoenix.
- **Why OpenInference attribute keys:** Phoenix's UI is built around them. Pick a custom schema and you get a less useful "list of attributes" view; pick OpenInference and Phoenix renders the LLM call shape, RETRIEVER chunks-as-cards, AGENT trace tree out of the box.
- **Why string truncation at 2000 chars:** our biggest inputs (synthesizer prompts with 5 chunks) regularly clear 3000 chars. Storing the full text in every span inflates Phoenix storage and the UI grows sluggish. Truncating with `…(+N chars)` keeps spans small and still readable.
- **Why `BatchSpanProcessor`:** the export is over HTTP — synchronous flushes per span would block the request hot path. The batch processor's default 5s queue is acceptable for dev visibility; for production we'd point at OTLP/gRPC on port 4317 and tune.

## Consequences

- The trace tree is what we said it'd be: a `query` root with `agent.router`, `agent.retrieve` (with `retrieval.hybrid` inside it), `agent.synthesize` (with `llm.complete` inside it) as children. All token counts, all retrieved doc IDs and scores, full input/output of every LLM call.
- Phoenix groups spans by the OTel `service.name` resource attribute, which we set to `agentstack`. Phoenix v7.9 buckets all spans into the `default` project regardless. The trace data is intact; only the project label is wrong. Fix is a Phoenix upgrade or switching to `arize-phoenix-otel`'s session API — neither blocks Week 3.
- The Celery worker does **not** emit spans (no tracer is configured in the worker). Ingestion + eval traces are out of scope for Week 3; if we need them, they're a straightforward `configure_tracing()` call at worker boot. The cost is one more reason for spans on the api side to stay separate.
- Streaming responses emit a single `llm.stream` span at the end of the generator with the concatenated output. Per-token spans would explode span count without adding insight.

## Out of scope

- Worker-side instrumentation (ingestion, eval) — Week 4 if needed.
- Per-tenant trace separation in Phoenix UI.
- Sampling — currently we trace 100% of traffic; for production we'd add a parent-based sampler.
- Metrics over OTel — we already ship Prometheus, no need to dual-emit.

## Revisit when

- Phoenix gains better cross-project routing (the current `service.name=agentstack` not landing in its own project is annoying).
- We need to trace the worker (heavy ingestion jobs would benefit).
- Span count per query grows past ~20 — we'd need sampling at the SDK level.
