# Benchmarks

Measured 2026-10-23 on the local Docker Compose stack (12-core Linux host, Docker VM capped at 4.5 GB, CPU-only embeddings). Every number below is reproducible from `benchmarks/`; raw outputs are in `benchmarks/results/`.

## Headline numbers

| Area | Metric | Result |
|---|---|---|
| Answer quality | Faithfulness, platform auto-eval (primary model) | **0.98** (offline re-score: 0.986) |
| | Citation accuracy, platform auto-eval (primary model) | **0.93** |
| | Answer relevancy | **0.88** |
| | Keyword-verified correct answers | **91%** (31/34) |
| | Answers carrying ≥1 citation | **97%** |
| | Answer cites the correct source doc | **94%** |
| Retrieval (n=35) | Hit@5, doc-level (dense / hybrid) | **1.00 / 1.00** |
| | MRR@5 (dense / hybrid) | **0.957 / 0.910** |
| | Hybrid retrieval latency | p50 **65 ms**, p95 **130 ms** |
| Caching | Exact-cache hit latency vs. cold query | p50 **22 ms vs 2.1 s** (~95× faster) |
| | Semantic-cache hits on paraphrases | **11/11**, p50 **80 ms** |
| | Semantic-cache false positives on 35 distinct questions | **0** |
| Platform under load | 10 concurrent users | **31 req/s**, p50 **24 ms**, p95 **49 ms**, 0 errors |
| | 50 concurrent users (single uvicorn process) | **70 req/s** saturation, p95 870 ms, 0 errors / 4,152 requests |
| Ingestion | 14 markdown docs, 9k words → 192 chunks | **29 s** end to end (~29 docs/min, 6.7 chunks/s) via Celery |
| Multi-tenancy | Cross-tenant access attempts blocked | **5/5** (all 404) |
| Rate limiting | Requests admitted at 60/min limit | exactly **60/75**, first 429 on request 61 |
| Resilience | Cold queries failing with a 500 when Groq throttles | 1/35 → **0/35** after model fallback (79 calls rerouted) |
| Tests | Unit / integration | **107/107** pass, 54% line coverage / **8/8** pass (voice test excluded, see below) |
| Frontend | `tsc --noEmit` + `next build` | clean, 9 routes, 105 kB shared first-load JS |

## Method

**Corpus.** The project's own documentation: 11 ADRs, `docs/architecture.md`, `README.md`, `CONTRIBUTING.md`. Ingested through the real API into a fresh collection (recursive chunker, 512/64, `bge-small-en-v1.5`).

**Golden set.** `benchmarks/golden_docs.json` holds 35 hand-written questions over the ADRs. Each item lists the source document(s) that answer it and keyword groups a correct answer must contain (e.g. q16 → `rrf_k` must be `60`). 11 items also carry a light paraphrase for the semantic-cache test.

**End to end** (`benchmarks/run_e2e.py`). Three sequential passes through `POST /api/v1/query` with web search off:
1. *Cold* — each question once; latency, citations, keyword check, and the auto-enqueued eval row.
2. *Exact replay* — same questions verbatim → exact-cache path.
3. *Paraphrase* — reworded questions → semantic-cache path.

It then registers a second user and probes five routes against the first user's collection, and fires 75 requests from a fresh non-admin user to check the rate limiter.

**LLM judge** (`benchmarks/rescore_eval.py`). Uses the production `faithfulness` / `citation_accuracy` code in the worker container, paced to stay under Groq's quota (see caveats). Scored twice: once on the 240-char `content_preview` the production eval pipeline feeds the judge, once on the full chunk text from Qdrant.

**Retrieval ablation** (`benchmarks/retrieval_ablation.py`). Runs inside the api container against the same collection. Doc-level relevance: a hit means a top-k chunk comes from a labelled source document.

**Load** (`benchmarks/locustfile.py`). Health, `/auth/me`, collection and document listing, and queries that are served from cache. This isolates the platform (auth middleware, rate limiter, Postgres, Redis, cache) from Groq's throughput. 10 users × 45 s and 50 users × 60 s, 0.1–0.5 s think time.

## Retrieval ablation

| Method | Hit@1 | Hit@3 | Hit@5 | MRR@5 | p50 ms |
|---|---|---|---|---|---|
| Dense (bge-small, Qdrant) | **0.914** | 1.000 | 1.000 | **0.957** | 51 |
| BM25 (production: 240-char previews) | 0.771 | 0.886 | 0.943 | 0.835 | 3 |
| Hybrid RRF (production) | 0.829 | 1.000 | 1.000 | 0.910 | 65 |
| BM25 over full chunk text | 0.743 | 0.914 | 0.943 | 0.831 | 1 |
| Hybrid RRF with full-text BM25 | 0.886 | 0.971 | 0.971 | 0.924 | 43 |
| Hybrid RRF + bge-reranker-base (production: rerank fused top-5) | 0.886 | 0.971 | 1.000 | 0.925 | 1,438 |
| Hybrid RRF + bge-reranker-base (fused top-20 → top-5) | 0.886 | 0.971 | 0.971 | 0.929 | 5,508 |

On this corpus — natural-language questions over prose — dense retrieval alone ranks best, and equal-weight RRF lets the weaker BM25 list pull a correct top-1 down to #2 on 3 of 35 questions. Recall is unaffected: every method that includes dense finds the right document in the top 3. The cross-encoder recovers 2 of those 3 (+5.7 pts Hit@1 over hybrid) but costs ~1.4 s per query on CPU, and widening its pool to 20 buys nothing here. Hybrid's advantage is identifier-heavy queries (error codes, function names), which this golden set barely contains; a keyword-heavy slice is the next thing to add before tuning RRF weights or turning the reranker on.

## Caching

| Path | n | p50 | p95 |
|---|---|---|---|
| Cold (LLM) | 26 single-attempt | 2,161 ms | 13,593 ms* |
| Exact cache | 34 | 22 ms | 26 ms |
| Semantic cache (paraphrase) | 11 | 80 ms | 113 ms |

\* Cold p95 is dominated by Groq rate-limit back-off, not by the platform (see caveats). Server-side latency for exact hits rounds to 0–1 ms; the rest is HTTP + auth middleware.

## Findings surfaced by this run

Found while benchmarking. **Fixed** items were re-measured after the fix (see the next section).

1. ✅ Fixed — **Eval feeds the judge truncated context.** `core/eval/runner.py` builds judge contexts from `chunk_metadata.content_preview`, which is capped at 240 chars (avg 223). Faithfulness scored 0.716 on previews vs 0.986 on full chunk text — the production metric under-reports by ~27 points.
2. ✅ Fixed — **`citation_accuracy` misaligns indices.** Answer markers `[n]` index the retrieved top-k, but the runner passes only the *cited* chunks, deduplicated and re-ordered. `[4]` in a two-citation answer falls off the end and scores as wrong. Production reports 0.525; index-aligned it is 0.907.
3. **BM25 indexes previews, not chunks** (ADR-007 by design) — a 240-char window of a ~512-char chunk.
4. ✅ Fixed — **Enabling the reranker OOM-kills the API.** `HybridRetriever` constructs a new `CrossEncoderReranker()` per query and the model is cached on the instance, so every query reloads 1.1 GB of weights. The ablation process was OOM-killed in the 4.5 GB container until it reused one instance. Separately, the fused list is truncated to `top_k` *before* reranking, so the cross-encoder can only reorder, never promote a chunk from rank 6–20 (no measured cost on this corpus).
5. ✅ Fixed — **No LLM fallback.** `get_fallback_chat_client()` exists but is never called. Groq 404s (retired model) and exhausted 429s surface to the client as HTTP 500.
6. **Single uvicorn process.** The 70 req/s ceiling at 50 users is one event loop; `--workers` is not set. Each worker loads its own models, so scaling out needs more than the current 4.5 GB VM.
7. **Integration test gaps.** ✅ Eval polling fixed; `test_eval_e2e::test_query_writes_eval_row` stops polling on the first `200 {"status": "pending"}` and asserts on an empty row; `test_voice_ws` writes Piper models to `/models` on the host and only works inside the container.
8. ✅ Fixed — **`pytest` crashed at startup** with the current `uv.lock`: `arize-phoenix-client` registers a pytest plugin that imports Phoenix, which breaks on `graphql-core` 3.3. `-p no:phoenix` is now in pytest `addopts`, so `make test` and CI work unchanged.
9. ✅ Fixed — **Fallback answers lost their citations.** `gpt-oss-120b` cites as `【n】`, which the `[n]` parser ignored. Markers are now normalized before extraction (see below).

## After the fixes

What changed:
- **Eval context.** `evaluate_and_persist` now judges against full chunk text from Qdrant (previews only as a fallback), and passes `citation_accuracy` a context list aligned to the answer's `[n]` markers.
- **Reranker.** `get_reranker()` keeps one `CrossEncoderReranker` per process. Ten reranked queries through `HybridRetriever` held peak RSS flat at 1.7 GB: an 11 s first-load, then ~1 s per query on CPU.
- **Fallback.** `FallbackChatClient` reroutes the primary's 429 / 404 / 5xx / connection errors to `GROQ_FALLBACK_MODEL`. The primary runs with `max_retries=0`, so throttling reroutes at once instead of after SDK backoff. Streams fall back only before the first token, so two answers are never spliced. If both models are exhausted the API returns **503**, not 500. Reroutes are counted in `agentstack_llm_fallbacks_total`.

Re-running `run_e2e.py` on the patched stack (`benchmarks/results/e2e_after_fixes.json`):

| Metric | Before | After |
|---|---|---|
| Cold-pass HTTP errors | 1 / 35 | **0 / 35** |
| Auto-eval faithfulness, primary model | 0.716 (14 scored) | **0.980** (22 scored) |
| Auto-eval citation accuracy, primary model | 0.525 | **0.932** |
| Cold p50 latency, primary model | 2.16 s | **1.25 s** |

**Fallback citation format.** In that run the fallback model answered 7 of the 35 questions and only 3 of them carried citations. The cause was format, not omission: `gpt-oss-120b` cites as `【2】` / `【2†L3-L5】`, which the `[n]` parser ignored. `normalize_citation_markers()` now rewrites both to `[n]` before extraction, and streamed tokens get the same bracket mapping so the UI renders chips live. Final run (`benchmarks/results/e2e_final.json`):

| Fallback-model answers | Before normalization (n=7) | After (n=9) |
|---|---|---|
| Carry ≥1 citation | 43% | **89%** |
| Cite the correct source doc | 43% | **89%** |
| Citation accuracy | 0.43 | **0.74** |
| Keyword-verified correct | 86% | 67% |

All 35 questions in the final run: **0 errors**, citations on **97%** of answers, source hit **0.94**, auto-eval faithfulness **0.99** (25 scored), citation accuracy **0.88**, answer relevancy **0.88**. The primary model alone: keyword accuracy 0.96, faithfulness 0.99, citation accuracy 0.93. Fallback answers are still less often fully correct (6 of 9 by keyword check), which is the cost of answering instead of failing. Latency in this run (cold p50 3.0 s) is inflated: the run overlapped a Docker image build that was saturating the network.

## Caveats

- **Model.** Groq retired `qwen/qwen3-32b` and `llama-3.3-70b-versatile`; this run used `qwen/qwen3.8-27b` as primary and as the eval judge.
- **Groq quota.** The on-demand tier caps `qwen/qwen3.8-27b` at 1,000 output tokens/min. Eval jobs compete with live queries for that budget: 8 of 35 cold queries needed client retries, 1 failed outright (q22), and auto-eval faithfulness came back null for 20 of 34 answers. Faithfulness above is from the paced re-score.
- **Small n.** 35 questions over 14 docs; one question moves Hit@1 by 2.9 points. Treat retrieval deltas under ~6 points as noise.
- **Self-judged.** The same model generates and judges. Keyword checks are an independent, model-free cross-check (91%).
- **Doc-level labels.** q14 cited `README.md`, which also answers it; scored as a miss.
- **Static-analysis debt.** `ruff`: 24 findings (15 auto-fixable). `mypy`: 10 → 6 errors after fixing the `ChatClient.stream` Protocol signature.

## Reproduce

```bash
make up
export DEV_API_KEY=$(grep ^DEV_API_KEY= .env | cut -d= -f2-)

uv run python benchmarks/run_e2e.py --keep            # prints the bench collection id
docker compose cp benchmarks worker:/tmp/benchmarks
docker compose exec worker python /tmp/benchmarks/rescore_eval.py /tmp/benchmarks/results/e2e.json full
docker compose cp benchmarks api:/tmp/benchmarks
docker compose exec api python /tmp/benchmarks/retrieval_ablation.py <collection_id>   # --no-rerank to skip the 1.1 GB cross-encoder
BENCH_COLLECTION_ID=<collection_id> uv run locust -f benchmarks/locustfile.py \
  --host http://localhost:8000 --headless -u 50 -r 10 -t 60s --csv benchmarks/results/load
uv run pytest -m unit --cov=agentstack
```
