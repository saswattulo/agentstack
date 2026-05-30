# AgentStack

> Self-hosted, production-grade multi-agent RAG platform. Upload documents → ingest → ask questions → get cited answers from an agentic pipeline with eval and full traces.

[![ci](https://img.shields.io/badge/ci-pending-lightgrey)](.github/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What it does

1. **Ingest** PDFs, markdown, plain text, and URLs into per-user *collections*.
2. **Chunk + embed** documents with a configurable strategy (recursive vs semantic) and a local sentence-transformer.
3. **Index** chunks in Qdrant with rich metadata payloads.
4. **Query** via an agentic pipeline (LangGraph) that routes between retrieval, web search, and synthesis.
5. **Cite** every claim back to its source chunk.
6. **Evaluate** answers automatically (RAGAS faithfulness + custom citation accuracy).
7. **Observe** every step via Phoenix traces + Prometheus + Grafana.

## Architecture

```
Client ──► FastAPI Gateway ──┬──► /ingest ──► Celery ──► parse · chunk · embed · upsert ──► Qdrant
                             │
                             └──► /query  ──► LangGraph
                                              ├── Router  (classify intent)
                                              ├── Retrieve  (hybrid: dense + BM25 + rerank)
                                              ├── Web search  (Tavily)
                                              ├── Code exec  (stub)
                                              ├── Synthesize  (with citations)
                                              └── Reflect  (self-check, retry)
                                                       │
                                                       ▼
                                  Postgres  (metadata · audit · eval results)
                                  Redis     (LLM cache · rate limit · Celery)
                                  Phoenix   (LLM traces)
                                  Prom+Graf (latency · tokens · cache hit rate)
```

Full diagram and rationale in [docs/architecture.md](docs/architecture.md). Design decisions are recorded as [ADRs](docs/adrs/).

## Quickstart

Requires Docker, Docker Compose, and Python 3.12 with [uv](https://docs.astral.sh/uv/).

```bash
# 1. Clone + set up env
cp .env.example .env
# ↪ set GROQ_API_KEY and TAVILY_API_KEY at minimum

# 2. Bring up the stack
make up

# 3. Apply migrations
make migrate

# 4. Tail logs
make logs
```

Visit:

- API:      http://localhost:8000/docs
- Qdrant:   http://localhost:6333/dashboard
- Phoenix:  http://localhost:6006
- Grafana:  http://localhost:3001 (admin/admin)

## Try it

Two ways to authenticate. Pick one.

### A) Real end user (recommended once you're testing the platform)

```bash
# Register → returns a JWT
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","name":"Me","password":"strong-pass-123"}' \
  | jq -r .access_token)

AUTH="Authorization: Bearer $TOKEN"

# Create a collection (private to me)
COLLECTION=$(curl -s -X POST http://localhost:8000/api/v1/collections \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"my-docs","description":"local test"}' | jq -r .id)

# Ingest a PDF
curl -X POST http://localhost:8000/api/v1/collections/$COLLECTION/ingest \
  -H "$AUTH" -F "file=@./tests/fixtures/sample.pdf"

# Start a conversation and query it (stub answer until Week 2)
CONV=$(curl -s -X POST http://localhost:8000/api/v1/conversations \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"First chat"}' | jq -r .id)

curl -X POST http://localhost:8000/api/v1/query \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"collection_id\":\"$COLLECTION\",\"conversation_id\":\"$CONV\",\"question\":\"What is chapter 3 about?\"}"

# See the whole conversation history later
curl http://localhost:8000/api/v1/conversations/$CONV -H "$AUTH"
```

### B) Local dev shortcut

In `APP_ENV=dev` the server auto-seeds a `dev@agentstack.local` user and binds `DEV_API_KEY` to them. Same scope as a logged-in user — convenient for scripts and CI:

```bash
curl http://localhost:8000/api/v1/collections -H "X-API-Key: $DEV_API_KEY"
```

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI + Pydantic v2 (async) |
| Agent | LangGraph |
| LLM | Groq (`qwen/qwen3-32b` default, `llama-3.3-70b-versatile` fallback) |
| Embeddings | sentence-transformers (`BAAI/bge-small-en-v1.5`, local CPU) |
| Vector store | Qdrant (Docker) |
| DB | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Cache + queue | Redis 7 + Celery 5 |
| Web search | Tavily |
| Tracing | Arize Phoenix (self-hosted) |
| Metrics | Prometheus + Grafana |
| Eval | RAGAS + custom citation-accuracy metric |
| Frontend | Next.js (Week 4) |
| Toolchain | uv |

## Build status

This repo is built week-by-week. Week 1 is fully implemented; Weeks 2–4 are scaffolded with interfaces and TODOs.

- ✅ **Week 1** — Foundation: API gateway, ingestion pipeline, Qdrant indexing
- 🟡 **Week 2** — Agentic RAG (LangGraph router + hybrid retrieval + streaming)
- 🟡 **Week 3** — Eval (RAGAS) + caching + Phoenix tracing + Prom metrics
- 🟡 **Week 4** — Next.js frontend + auth hardening + CI/CD + load tests

See [CLAUDE.md](CLAUDE.md) for the working-status checklist.

## Development

```bash
make install      # uv sync --all-extras
make dev          # run API locally (no Docker)
make test         # full test suite
make test-unit    # unit only — no Docker required
make lint         # ruff
make fmt          # ruff format + autofix
make typecheck    # mypy
make load-test    # locust against localhost:8000
```

Set up pre-commit hooks once:

```bash
uv run pre-commit install
```

## Project layout

```
src/agentstack/      Python package
  api/               FastAPI routes, middleware, deps
  core/              Domain: ingestion, retrieval, agent, eval
  models/            SQLAlchemy ORM
  schemas/           Pydantic request/response
  services/          Business logic layer
  workers/           Celery tasks
  infra/             LLM, vector store, metrics, tracing, db, redis
alembic/             Migrations
tests/               unit / integration / load
docs/                Architecture + ADRs
frontend/            Next.js (Week 4)
grafana/             Pre-built dashboard
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
