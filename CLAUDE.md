# CLAUDE.md — Working Notes for AgentStack

This file is loaded into Claude Code's context for every session in this repo. Keep it small, current, and load-bearing.

## What this project is

Multi-agent, **multi-user** RAG platform. Users register, upload documents into per-user collections → query through a LangGraph agent that routes between retrieval, web search, code execution, and synthesis → cited answers with eval + observability. Chat lives in conversation threads owned by the user.

Built as a portfolio project. The interview signal comes from production patterns (queues, multi-level caching, eval, tracing, CI/CD, real auth + tenancy), not raw lines of code.

## Tech stack — locked decisions

| Concern | Choice | Notes |
|---|---|---|
| Toolchain | **uv** | `uv sync`, `uv run`. Lockfile = `uv.lock`. Don't reach for pip/poetry. |
| Python | 3.12 | Pin in `pyproject.toml`. |
| API | FastAPI + Pydantic v2 | Async everywhere. |
| DB | Postgres 16 + SQLAlchemy 2 async + Alembic | `asyncpg` for the API, `psycopg` for the Celery worker. |
| Cache + queue | Redis 7 | Single Redis, separate DB indices: cache/rate-limit, Celery broker, Celery results. |
| Vector store | Qdrant | Hybrid (dense + sparse) ready. Do NOT swap to Chroma. |
| Task queue | Celery 5 | Async ingestion + background eval. |
| LLM | **Groq only** | Default model `qwen/qwen3-32b`, fallback `llama-3.3-70b-versatile`. **OpenAI / Anthropic SDKs are not installed — do not import them.** |
| Embeddings | **sentence-transformers local** | Default `BAAI/bge-small-en-v1.5` (384 dim). Runs on CPU. |
| Reranker | `BAAI/bge-reranker-base` (Week 2/stretch) | Off by default. |
| Web search | Tavily | Key in `.env` (`TAVILY_API_KEY`). |
| Code exec node | **stub only** | Router can route to it, but it returns "not enabled". |
| **Auth** | **JWT (HS256) for users + API keys for machine clients.** Argon2id for password hashing. See ADR-006. |
| **Tenancy** | **Per-user private collections + per-user conversations.** Every resource has a user owner. |
| Tracing | Arize Phoenix (self-hosted in Compose) | Don't wire LangSmith. |
| Metrics | Prometheus + Grafana | Custom domain metrics in `infra/metrics.py`. |
| Frontend | Next.js (Week 4) | Scaffolded under `frontend/`. |
| Deploy | Local Docker Compose only | No Fly/Railway/K8s yet. CI builds + pushes images to GHCR. |

## Auth model (ADR-006)

- `users` table — email (unique), name, password_hash (argon2id), is_active, is_admin.
- `POST /api/v1/auth/register` → returns JWT + user.
- `POST /api/v1/auth/login` → returns JWT + user.
- `GET /api/v1/auth/me` → current user (requires auth).
- `POST /api/v1/auth/api-keys` → mint a machine credential bound to the current user. The raw key is shown **once**; only the hash is stored.
- Auth middleware accepts EITHER `Authorization: Bearer <jwt>` OR `X-API-Key: <key>`. Both resolve to a `user_id`. Routes use `CurrentUserDep` regardless of which method authed.
- Dev bootstrap: in `APP_ENV=dev`, startup seeds a `dev@agentstack.local` user and binds `DEV_API_KEY` to them. `make up` still works without a manual register step.

## Repo layout (canonical)

```
src/agentstack/
  main.py             # FastAPI app factory + lifespan + dev-user bootstrap
  config.py           # Pydantic Settings (BaseSettings)
  api/
    routes/           # auth, conversations, collections, ingest, documents, query, eval, health
    middleware/       # AuthMiddleware, RateLimitMiddleware, RequestIDMiddleware
    deps.py           # CurrentUserDep, DbSession, etc.
  core/
    ingestion/        # parser, chunker, embedder
    retrieval/        # hybrid, reranker, cache
    agent/            # graph, nodes, tools, prompts
    eval/             # metrics, runner, golden
  models/             # SQLAlchemy ORM — User, ApiKey, Collection, Document, ChunkMetadata, Conversation, QueryLog, EvalResult
  schemas/            # Pydantic request/response (user, conversation, collection, document, query, common)
  services/           # password, jwt_service, user_service, conversation_service, api_key_service, bootstrap, query_service
  workers/            # Celery app + tasks
  infra/              # llm, vectorstore, metrics, tracing, db, redis, logging
```

## Conventions

- **Imports**: always absolute (`from agentstack.config import settings`), never relative.
- **Settings**: import `settings` from `agentstack.config`. Never read `os.environ` directly outside `config.py`.
- **Async**: all I/O is async. Sync code only inside Celery tasks and inside CPU-bound helpers (embedding, parsing).
- **DB sessions**: via the `DbSession` dep, never ad hoc engines.
- **LLM calls**: `agentstack.infra.llm.get_chat_client()`. Don't import `groq.Groq` in feature code.
- **Vector store**: `agentstack.infra.vectorstore.get_qdrant()` / `_sync()`. Don't import `QdrantClient` in feature code.
- **Auth**: routes get `current: CurrentUserDep`. **Every resource query MUST filter by `current.id`** (or join through an owned parent). There's no "list all collections globally" — that would be a multi-tenant bug.
- **Errors**: raise from `agentstack.api.errors`. Don't return ad hoc `{"error": ...}` dicts.
- **Logging**: structlog. `logger = structlog.get_logger(__name__)`. No `print`.
- **Tests**: marker required. `@pytest.mark.unit` or `@pytest.mark.integration`.

## What's implemented vs stubbed

| Week | Feature | Status |
|---|---|---|
| 1 | Project scaffolding, Docker, settings | ✅ Real |
| 1 | Health endpoint, AuthMiddleware (JWT + API key), request ID | ✅ Real |
| 1 | Postgres models + Alembic | ✅ Real |
| 1 | Users, register/login/me, API key issue/revoke | ✅ Real |
| 1 | Conversations (CRUD + message listing) | ✅ Real |
| 1 | Collections CRUD (per-user owned) | ✅ Real |
| 1 | Ingestion (parse, chunk, embed, Qdrant upsert) via Celery | ✅ Real |
| 1 | Per-user dev bootstrap | ✅ Real |
| 2 | LangGraph router + retrieval + synthesis | ✅ Real |
| 2 | Hybrid retrieval (dense + BM25 + RRF) | ✅ Real (see ADR-007) |
| 2 | Cross-encoder reranker | ✅ Real (opt-in via `RERANKER_ENABLED`) |
| 2 | Web search tool (Tavily) | ✅ Real (gated on `TAVILY_API_KEY`) |
| 2 | Code execution tool | 🟡 Stub (returns "not enabled") |
| 2 | Streaming `/query/stream` (SSE) | ✅ Real |
| 2 | Conversation memory: prior-turns injection | ✅ Real (sliding window, last 5 Q&A) |
| 2 | Conversation memory: summary compression | 🟡 Stub (column exists; Week 4) |
| 3 | Eval pipeline (faithfulness + answer relevancy + citation accuracy) | ✅ Real (custom LLM-judge; not RAGAS — see ADR-008) |
| 3 | Auto-enqueue eval after every non-cached query | ✅ Real |
| 3 | Phoenix tracing on the hot path (LLM, retrieval, agent nodes) | ✅ Real (OpenInference attrs; see ADR-008) |
| 3 | Semantic + exact LLM cache w/ ingestion invalidation | ✅ Real (per-collection LRU; see ADR-009) |
| 3 | Rate limiting (sliding-window log, admin bypass) | ✅ Real (60/min default) |
| 3 | Prometheus custom metrics | ✅ Real (HTTP via instrumentator; domain via `infra/metrics.py`) |
| 3 | Phoenix project bucketing for non-default service.name | 🟡 Known quirk — traces land in `default` project |
| 3 | Worker-side Prom gauges visible in api `/metrics` | 🟡 Known limitation — separate process registries |
| 4 | Next.js frontend | 🟡 Stub (minimal scaffold) |
| 4 | CI workflow | ✅ Real |
| 4 | Load test (locust) | 🟡 Stub |

## Common commands

```bash
make up              # bring up postgres, redis, qdrant, phoenix, prometheus, grafana, api, worker
make migrate         # alembic upgrade head
make logs            # tail everything
make test            # all pytest
make test-unit       # unit only (no docker required)
make lint            # ruff
make fmt             # ruff format + autofix
make typecheck       # mypy
make nuke            # destructive: down -v, wipes volumes
```

## Service URLs (local)

- API: http://localhost:8000 (Swagger at `/docs`)
- Qdrant dashboard: http://localhost:6333/dashboard
- Phoenix: http://localhost:6006
- Grafana: http://localhost:3001 (admin/admin)
- Prometheus: http://localhost:9090

## Don'ts

- **Don't install OpenAI or Anthropic SDKs.** Groq-only for now.
- **Don't add Chroma.** Qdrant is the choice.
- **Don't bypass `agentstack.config.settings`.** Add new fields there.
- **Don't list/query a resource without an `owner_id == current.id` filter.** That's a tenant-isolation bug.
- **Don't store raw API keys.** Hash with SHA-256 (`hash_api_key`) and only return the raw value at creation.
- **Don't write multi-paragraph docstrings or comment blocks.** Global comment policy: one short line when WHY is non-obvious; otherwise nothing.
- **Don't commit `.env`**, real API keys, model artifacts, or `data/`.
- **Don't use `--no-verify`** when committing. If a hook fails, fix the underlying issue.
- **Don't auto-commit.** The user commits manually.
