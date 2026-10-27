# AgentStack

> Self-hosted, multi-user agentic RAG platform. Upload documents into private collections, ask questions in chat or by voice, and get cited answers. Every answer is scored, traced and cached.

[![ci](https://github.com/saswattulo/agentstack/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What it does

1. **Multi-user by default.** Register / log in (JWT), or use per-user API keys for scripts. Every collection, document, conversation and query log belongs to exactly one user.
2. **Ingest** PDFs, markdown, text and URLs asynchronously through Celery: parse → chunk (recursive or semantic) → embed locally → upsert into Qdrant.
3. **Answer** through a LangGraph agent. A router picks retrieval, web search or code execution (stub). Hybrid retrieval combines dense, BM25 and Reciprocal Rank Fusion, with an optional cross-encoder rerank. The synthesizer cites every claim as `[n]`.
4. **Stay up when the LLM doesn't.** Groq 429 / 404 / 5xx errors reroute to a fallback model. If both are exhausted the API returns 503, not a crash.
5. **Cache** answers at two levels: exact (22 ms) and semantic paraphrase (~90 ms), scoped per collection and invalidated on ingest.
6. **Evaluate** every fresh answer in the background with an LLM judge: faithfulness, answer relevancy, citation accuracy.
7. **Observe** every request through Phoenix traces (OpenInference), Prometheus domain metrics and a Grafana dashboard.
8. **Talk to it.** Voice runs over one WebSocket: silero VAD → Groq Whisper → the same agent → per-sentence Piper TTS. You can interrupt it mid-answer.

## Architecture

```
Next.js UI ──► FastAPI  (CORS · RequestID · Auth: JWT | X-API-Key · rate limit)
                 │
                 ├─ /collections/{id}/ingest ──► Celery ──► parse · chunk · embed ──► Qdrant + Postgres
                 │
                 ├─ /query · /query/stream (SSE) ──► LLM cache (exact → semantic) ──hit──► answer
                 │                                     │ miss
                 │                                     ▼
                 │                       LangGraph:  router ─┬─► retrieve (dense + BM25 → RRF [→ rerank])
                 │                                           ├─► web search (Tavily; also on empty retrieval)
                 │                                           └─► code exec (stub)
                 │                                                   ▼
                 │                                     synthesize with [n] citations ─► reflect (pass-through)
                 │                                                   │
                 │                         Groq primary ──429/404/5xx──► Groq fallback
                 │                                                   ▼
                 │                     QueryLog ─► Celery eval (LLM judge) ─► EvalResult
                 │
                 └─ /voice/stream (WebSocket) ──► VAD ─► Whisper ─► same agent ─► Piper TTS ─► audio

Postgres  users · keys · collections · documents · chunks · conversations · query logs · eval
Redis     LLM cache · rate limits · Celery broker/results
Phoenix   traces        Prometheus + Grafana   latency · tokens · cache · fallbacks · eval
```

Details in [docs/architecture.md](docs/architecture.md). Every significant decision is recorded as an [ADR](docs/adrs/).

## Benchmarks

Measured on the local Compose stack, using a 35-question golden set written over the project's own docs. Method, ablations and caveats: [docs/benchmarks.md](docs/benchmarks.md).

| Metric | Result |
|---|---|
| Faithfulness / citation accuracy (platform auto-eval) | 0.98 / 0.93 |
| Answer relevancy | 0.88 |
| Keyword-verified correct answers | 91% |
| Retrieval Hit@5 / MRR@5 (hybrid) | 1.00 / 0.91 |
| Exact-cache hit vs cold query, p50 | 22 ms vs 2.1 s (~95×) |
| Semantic-cache paraphrase hits / false positives | 11/11 / 0 |
| Platform latency at 10 users (p50 / p95) | 24 ms / 49 ms, 0 errors |
| Saturation, single uvicorn process | 70 req/s, 0 errors at 50 users |
| Cross-tenant access attempts blocked | 5/5 |
| Cold-query errors under Groq throttling (with model fallback) | 0/35 |
| Tests | 107/107 unit (54% coverage), 8/8 integration |

## Quickstart

Requires Docker + Compose, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 20+ for the UI.

```bash
cp .env.example .env        # set GROQ_API_KEY (required) and TAVILY_API_KEY (web search)
make up                     # postgres, redis, qdrant, phoenix, prometheus, grafana, api, worker
make migrate                # alembic upgrade head

cd frontend && npm install && npm run dev    # UI at http://localhost:3000
```

| Service | URL |
|---|---|
| UI | http://localhost:3000 |
| API + Swagger | http://localhost:8000/docs |
| Qdrant | http://localhost:6333/dashboard |
| Phoenix | http://localhost:6006 (traces land in the `default` project; see ADR-008) |
| Grafana | http://localhost:3001 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Postgres / Redis (host side) | `localhost:5442` / `localhost:6390`; run `make ports` |

The first image build is large (CUDA builds of torch). On a slow or flaky network, `docker build --network=host` is more reliable than `docker compose build`.

## Try it from the CLI

```bash
# Register → JWT
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email":"me@example.com","name":"Me","password":"strong-pass-123"}' | jq -r .access_token)
AUTH="Authorization: Bearer $TOKEN"

# Private collection + ingest one of this repo's ADRs
COLL=$(curl -s -X POST localhost:8000/api/v1/collections -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"agentstack-docs"}' | jq -r .id)
curl -s -X POST localhost:8000/api/v1/collections/$COLL/ingest -H "$AUTH" \
  -F "file=@docs/adrs/007-retrieval-strategy.md"

# Ask (repeat it to see cache_hit=true)
curl -s -X POST localhost:8000/api/v1/query -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"collection_id\":\"$COLL\",\"question\":\"Why is RRF used instead of a linear score blend?\"}" | jq

# Background eval for that answer (poll until status is "ready")
curl -s localhost:8000/api/v1/eval/results/<query_id> -H "$AUTH" | jq
```

For scripts and CI, `APP_ENV=dev` seeds a `dev@agentstack.local` admin user bound to `DEV_API_KEY`: `curl localhost:8000/api/v1/collections -H "X-API-Key: $DEV_API_KEY"`. Admins bypass the 60/min rate limit.

## Status

Built in weekly increments. Weeks 1–5 are implemented and tested; the [CLAUDE.md](CLAUDE.md) status table is the canonical checklist.

| | Scope | Status |
|---|---|---|
| Week 1 | API, auth (JWT + API keys), multi-tenancy, Celery ingestion, Qdrant | ✅ |
| Week 2 | LangGraph agent, hybrid retrieval + RRF, reranker, Tavily, SSE streaming, conversation memory | ✅ |
| Week 3 | LLM-judge eval, Phoenix tracing, two-level cache, rate limiting, Prometheus | ✅ |
| Week 4 | Voice agent (VAD, Whisper, Piper, WebSocket, barge-in), CI | ✅ |
| Week 5 | Next.js UI: auth, streaming chat, citations, eval, collections, API keys, voice in chat | ✅ |
| Week 6 | Benchmarks; eval-pipeline fixes; LLM fallback + 503; reranker memory fix | ✅ |

Still stubbed: the code-exec tool, the reflect node (pass-through), conversation summarization, `GET /eval/aggregate` and `POST /eval/runs/{id}`, and the per-user voice-session cap.

## Tech stack

| Layer | Choice |
|---|---|
| API | FastAPI + Pydantic v2 (async) |
| Agent | LangGraph |
| LLM | Groq: `qwen/qwen3.8-27b`, falling back to `openai/gpt-oss-120b` |
| Embeddings / rerank | sentence-transformers, local CPU: `BAAI/bge-small-en-v1.5` / `BAAI/bge-reranker-base` (opt-in) |
| Vector store | Qdrant |
| DB | PostgreSQL 16 + SQLAlchemy 2 async + Alembic |
| Cache + queue | Redis 7 + Celery 5 |
| Auth | JWT (HS256) + SHA-256-hashed API keys, Argon2id passwords |
| Web search | Tavily |
| Eval | Custom LLM judge (faithfulness, answer relevancy) + citation accuracy; see ADR-012 |
| Voice | silero-vad, Groq Whisper, Piper TTS |
| Observability | Arize Phoenix, Prometheus, Grafana, structlog |
| Frontend | Next.js 15 App Router, Tailwind, React Query |
| Toolchain | uv, ruff, mypy, pytest, locust, GitHub Actions → GHCR |

## Development

```bash
make install           # uv sync --all-extras
make dev               # API locally without Docker
make test              # all tests (integration ones skip if the stack is down)
make test-unit         # unit only, no Docker
make lint / fmt / typecheck
uv run pre-commit install
```

Benchmarks (live stack required; full recipe in [docs/benchmarks.md](docs/benchmarks.md#reproduce)):

```bash
uv run python benchmarks/run_e2e.py --keep                     # quality, cache, isolation, rate limit
docker compose exec api python /tmp/benchmarks/retrieval_ablation.py <collection_id>
BENCH_COLLECTION_ID=<id> uv run locust -f benchmarks/locustfile.py --host http://localhost:8000 --headless -u 50 -t 60s
```

## Project layout

```
src/agentstack/      api/ (routes, middleware, deps) · core/ (ingestion, retrieval, agent, eval, voice)
                     models/ · schemas/ · services/ · workers/ · infra/ (llm, vectorstore, db, redis, metrics, tracing)
alembic/             migrations
tests/               unit/ · integration/ (live stack) · fixtures/ · load/
benchmarks/          golden set, e2e runner, retrieval ablation, judge re-score, locust profile, results/
frontend/            Next.js UI (see frontend/README.md)
infra/               prometheus.yml · grafana provisioning + dashboard
docs/                architecture.md · benchmarks.md · adrs/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT; see [LICENSE](LICENSE).
