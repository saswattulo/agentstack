# Architecture

## Goals

AgentStack is a self-hosted, production-style RAG platform. It must:

1. Serve many users with strict isolation. Every resource has one owner.
2. Ingest documents asynchronously and report per-document progress.
3. Answer through an agent that chooses between corpus retrieval, web search and (stubbed) code execution, and cite every claim.
4. Degrade, not fail, when the LLM provider throttles or retires a model.
5. Be observable end to end (traces, metrics, structured logs) and evaluable (every fresh answer is scored and persisted).
6. Run on one laptop with `make up`.

## System diagram

```
┌───────────────┐  HTTP / SSE / WS   ┌───────────────────────────────────────────────┐
│  Next.js UI    │──────────────────▶│ FastAPI                                        │
│  (React Query) │◀──────────────────│  CORS → RequestID → Auth (JWT | X-API-Key)     │
└───────────────┘                    │       → RateLimit (sliding window, Redis)      │
                                     └──┬───────────────┬────────────────────┬────────┘
                                        │               │                    │
                           ┌────────────▼───┐  ┌────────▼────────────┐  ┌────▼─────────────┐
                           │ /ingest         │  │ /query, /query/stream│  │ /voice/stream WS │
                           │ /collections    │  │ services.query_service│  │ VAD → Whisper    │
                           │ /documents      │  └────────┬────────────┘  │ → stream_query   │
                           └────────┬───────┘           │                │ → Piper TTS      │
                                    │          ┌────────▼─────────┐      └──────────────────┘
                           ┌────────▼───────┐  │ LLM cache (Redis) │
                           │ Celery worker   │  │ exact → semantic  │──hit──▶ answer
                           │ parse · chunk   │  └────────┬─────────┘
                           │ embed · upsert  │           │ miss
                           │ cache invalidate│  ┌────────▼──────────────────────────────┐
                           │ eval judge      │  │ LangGraph                              │
                           └──┬──────────┬──┘  │ router ─┬─ retrieve ─(empty)─┐         │
                              │          │     │         ├─ web_search ◀──────┘         │
                       ┌──────▼───┐ ┌────▼───┐ │         └─ code_exec (stub)            │
                       │ Qdrant    │ │Postgres│ │ → synthesize [n] → reflect (no-op)     │
                       │ col_<uuid>│ │        │ └────────┬──────────────────────────────┘
                       └──────────┘ └────────┘          │
                                                ┌────────▼─────────────────────────┐
                                                │ FallbackChatClient                │
                                                │ Groq primary ─429/404/5xx─▶ fallback │
                                                └──────────────────────────────────┘
        Observability: Phoenix (OTel spans, OpenInference keys) · Prometheus + Grafana · structlog
```

## Request flow: ingestion

1. `POST /api/v1/collections/{id}/ingest` (multipart) or `/ingest-url`. The route checks the collection belongs to the caller.
2. The upload is streamed to disk with a size guard, a `Document` row is created as `PENDING`, and `ingest_document_task` is enqueued.
3. The worker parses (pypdf / text / BeautifulSoup for URLs), chunks with the collection's strategy (`recursive` default, `semantic` optional; ADR-002), embeds with `bge-small-en-v1.5` (384-d) and upserts into Qdrant. It writes `chunk_metadata` rows (point id + 240-char preview) to Postgres and updates `Document.status` / `progress` per stage.
4. On completion the worker calls `invalidate_collection_sync()`, so cached answers can't outlive the corpus they came from (ADR-009).

## Request flow: query

1. `POST /api/v1/query` (JSON) or `/query/stream` (SSE over POST). The route verifies collection ownership and resolves an optional conversation owned by the caller.
2. `query_service` checks the LLM cache: exact key `sha256(question + collection)`, then cosine ≥ 0.95 against the collection's vector index. A hit returns at once with `cache_hit_kind`, and no eval is enqueued.
3. On a miss the LangGraph agent runs:
   - **Router** classifies intent (factual / analytical / comparison / web / code / conversational).
   - **Retrieve**: dense (Qdrant, oversample ×4) + BM25 over chunk previews, fused with RRF (`k=60`). The optional cross-encoder rerank (`RERANKER_ENABLED`) reorders the fused top-k (ADR-007).
   - Empty retrieval with web search allowed → **Tavily**.
   - **Synthesize** builds a numbered context block and prompts for `[n]` citations. The last 5 Q&A turns of the conversation are injected. Citation markers are normalized (`【n】` → `[n]`) before extraction.
   - **Reflect** is currently a pass-through.
4. All LLM calls go through `infra.llm.get_chat_client()`, a `FallbackChatClient` (ADR-005 addendum). The primary runs without SDK retries; 429 / 404 / 5xx / connection errors reroute to the fallback model. Streams only fall back before the first token. If both models fail the API returns 503.
5. A `QueryLog` row is written, the answer is cached (except for conversational intents) and `eval_query_task` is enqueued.
6. **Eval** (worker, ADR-012): faithfulness is LLM claim extraction plus verdicts against the cited chunks' **full text** from Qdrant. Answer relevancy is the cosine between the question and questions regenerated from the answer. Citation accuracy matches each `[n]` against the chunk it points to. The result goes to `eval_results`, readable via `GET /api/v1/eval/results/{query_id}` (`pending` until ready).

## Request flow: voice

One WebSocket per session (`/api/v1/voice/stream`); the JWT arrives in the first frame (ADR-010). The browser sends 16 kHz Int16 PCM frames. silero VAD segments utterances (800 ms silence), Groq Whisper transcribes, and the same `stream_query` path answers. Sentences are synthesized with Piper as they complete and sent back as WAV. An `interrupt` control frame, or a new transcript, cancels the in-flight turn.

## Tenancy and auth

- `users` (Argon2id passwords) · `api_keys` (SHA-256 hash only, bound to a user) · stateless HS256 JWT, 24 h.
- `AuthMiddleware` resolves either credential to `request.state.user_id`; routes use `CurrentUserDep`.
- Every query filters on `owner_id == current.id` or joins through an owned parent. Foreign resources return 404, not 403, so they can't be enumerated.
- Rate limit: 60 req/min per user (sliding-window log in Redis). Admins bypass it.

## Storage layout

- **Postgres:** users, api_keys, collections, documents, chunk_metadata, conversations, query_logs, eval_results. `query_logs` FKs are `ON DELETE SET NULL`, so audit rows outlive deleted collections.
- **Qdrant:** one collection per AgentStack collection (`col_<uuid>`), payload carries full chunk text plus `document_id`.
- **Redis:** DB 0 for cache + rate limits, DB 1 for the Celery broker, DB 2 for Celery results.
- **Volumes:** Phoenix traces, Piper voice model (`/models/piper`), Hugging Face model cache.

## Boundary contracts

- Routes and services never build DB / Redis / Qdrant / LLM clients ad hoc; everything goes through `infra/`.
- Feature code never imports `groq.AsyncGroq`; provider exceptions are translated in `infra.llm` (`LLMUnavailableError`).
- Prompts are versioned objects in `core/agent/prompts.py`.
- Heavy models are process singletons: `get_embedder()`, `get_reranker()`.

## Observability

- **Traces:** manual OTel spans with OpenInference keys: `query` → `agent.router` / `agent.retrieve` (`retrieval.hybrid`) / `agent.synthesize` (`llm.complete`), plus `asr.whisper` and `tts.piper`. The worker is not traced (ADR-008).
- **Metrics:** HTTP via `prometheus-fastapi-instrumentator`. Domain metrics in `infra/metrics.py`: ingestion, query latency, LLM tokens, `agentstack_llm_fallbacks_total`, cache hits/misses, retrieval sizes, eval gauges. Worker-side gauges live in the worker's own registry and don't appear on the API's `/metrics`.
- **Logs:** structlog, JSON in prod.

## Known limits

- One uvicorn process per API container. It saturates around 70 req/s (see `docs/benchmarks.md`). Each extra worker loads its own models, about 1.5 GB each.
- BM25 indexes the 240-char previews, not full chunks, and lives in a per-process cache.
- Same-model LLM judging; Groq's per-model token quotas can leave eval scores null under load.
- Images ship CUDA builds of torch even though everything runs on CPU.

## Non-goals (for now)

- Kubernetes or any hosted deployment.
- Real sandboxed code execution.
- Workspaces / sharing between users, OAuth, refresh tokens.
