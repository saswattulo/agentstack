# Architecture

## Goals

AgentStack is a self-hosted, production-style RAG platform. It must:

1. Ingest heterogeneous documents asynchronously and report per-document progress.
2. Answer questions through an agentic pipeline that can choose between corpus retrieval, web search, and (optionally) code execution.
3. Cite every claim to a source chunk.
4. Be observable end-to-end: every retrieval and LLM call must produce a trace.
5. Be evaluable: every answer should be scoreable, with metrics persisted for trend analysis.
6. Run on one developer laptop in under one command (`make up`).

## System diagram

```
┌──────────────┐      ┌────────────────────────────────────────────┐
│   Frontend    │─────▶│  FastAPI Gateway                           │
│   (Next.js)   │◀─────│  • RequestID, API-key auth, rate limit     │
└──────────────┘      │  • Pydantic v2 validation                  │
                      │  • Custom error taxonomy                   │
                      └────────────┬────────────┬──────────────────┘
                                   │            │
                  ┌────────────────▼┐    ┌──────▼──────────────────┐
                  │ POST /ingest     │    │ POST /query             │
                  │ + /collections   │    │  + /query/stream        │
                  └────────┬─────────┘    └──────┬──────────────────┘
                           │                     │
                  ┌────────▼─────────┐    ┌──────▼──────────────────┐
                  │ Celery worker    │    │ services.query_service  │
                  │  parse → chunk   │    │  → cache lookup         │
                  │  → embed → upsert│    │  → LangGraph agent      │
                  └────────┬─────────┘    │     • router            │
                           │              │     • hybrid retrieval  │
                  ┌────────▼─────────┐    │     • web search        │
                  │  Qdrant          │◀───│     • synthesis + cite  │
                  │  vector store    │    │     • reflect           │
                  └──────────────────┘    │  → eval enqueue         │
                                          └──────┬──────────────────┘
                  ┌──────────────────┐           │
                  │  PostgreSQL      │◀──────────┤
                  │  metadata · logs │           │
                  │  eval results    │   ┌───────▼─────────┐
                  └──────────────────┘   │ Eval runner      │
                                         │ RAGAS + citation │
                  ┌──────────────────┐   │ accuracy         │
                  │  Redis           │   └──────────────────┘
                  │  cache · queue   │
                  │  rate limit      │
                  └──────────────────┘
                                          ┌──────────────────────────┐
                                          │ Observability             │
                                          │  Phoenix (LLM traces)     │
                                          │  Prometheus + Grafana     │
                                          └──────────────────────────┘
```

## Request flow — ingestion

1. `POST /api/v1/collections/{id}/ingest` accepts a multipart upload.
2. The file is streamed to `/tmp/agentstack/uploads/<uuid>__<filename>` with a max-size guard.
3. A `Document` row is created with `status=PENDING`.
4. The endpoint enqueues `agentstack.workers.tasks.ingest_document_task` on the `ingest` queue.
5. The Celery worker runs `parse → chunk → embed → upsert → ChunkMetadata insert`, updating `Document.status` and `Document.progress` after each stage.
6. On completion, the temporary upload is deleted; chunks live in Qdrant + `chunk_metadata` in Postgres.

Failure modes:
- Parser exception → retry once, then `status=FAILED` with `error_message`.
- Embedder OOM → terminate worker; Celery requeue on restart (acks-late + prefetch-1).
- Qdrant unavailable → retry with exponential backoff (Celery built-in).

## Request flow — query (target shape; Week 2 implements)

1. `POST /api/v1/query` validates the request and authenticates via API key.
2. `services.query_service` checks the LLM cache (exact + semantic).
3. On miss, the LangGraph state machine runs:
   - **Router** classifies intent (factual / analytical / comparison / web / code / conversational).
   - **Retrieve** runs hybrid search (dense via Qdrant + BM25), then cross-encoder reranking.
   - If retrieval is empty or confidence is low → **Web search** node calls Tavily.
   - **Synthesize** prompts the LLM with retrieved context, instructing inline `[n]` citations.
   - **Reflect** checks for unsupported claims; on low confidence, loops back.
4. The answer + citations are returned. A `QueryLog` row is written synchronously.
5. An eval task is enqueued (fire-and-forget) which populates an `EvalResult` row.

## Storage layout

- **Postgres** holds relational state: collections, documents, chunk metadata, API keys, query logs, eval results.
- **Qdrant** holds vectors + payloads. One collection per AgentStack collection (`col_<uuid>`). Vector dim is locked to the collection's embedder at creation time.
- **Redis** is a single instance with separate DB indices: `0` for cache + rate limits, `1` for Celery broker, `2` for Celery results.
- **Phoenix** stores traces locally in a Docker volume.

## Boundary contracts

- Routes never construct DB engines / Redis clients / Qdrant clients ad hoc. They go through `infra/`.
- Feature code never imports `groq.AsyncGroq` directly. It goes through `infra.llm.get_chat_client()`.
- Prompts live in `core/agent/prompts.py`. They are versioned. New variants are new objects, not in-place edits.
- Tools (`core/agent/tools.py`) expose a JSON schema for the LLM and a Python callable. The agent picks the callable via `TOOL_REGISTRY`.

## Observability

- HTTP-layer metrics come from `prometheus-fastapi-instrumentator`.
- Domain metrics are defined in `infra/metrics.py` and incremented at known seams (ingestion stages, retrieval, eval).
- Tracing is wired in `infra/tracing.py`; Phoenix is the default collector. Switching to Jaeger only requires changing `PHOENIX_COLLECTOR_ENDPOINT` (OTLP-compatible).
- Logs are structured (structlog). In dev they're colorized; in prod they emit JSON.

## Non-goals (for now)

- Multi-tenant isolation beyond per-API-key rate limits.
- Live Kubernetes deployment.
- Real sandboxed code execution (the code-exec tool is stubbed).
- A fine-tuned reranker (stretch).
