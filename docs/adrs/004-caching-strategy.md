# ADR 004 — Caching: exact + semantic two-level

- **Status:** Accepted (interface) / Pending implementation (Week 3)
- **Date:** 2026-05-30

## Context

LLM calls dominate query cost and latency. A naive exact-match cache catches "same question twice" — which is rare in conversational use. Most repeat traffic is *paraphrased*: same intent, different wording. We want both layers.

## Decision

Two-level cache, both backed by Redis:

1. **Exact cache** — key = `sha256(question + collection_id)`. Constant-time lookup. Use for identical queries from clients with retry logic or naïve UIs.
2. **Semantic cache** — embed the query, scan a small Redis-stored index of recent (vec, key) pairs scoped to the collection, accept a hit if cosine similarity > `SEMANTIC_CACHE_THRESHOLD` (default 0.95).

Cache entries store: `answer`, `citations`, `model`. TTL = `CACHE_TTL_SECONDS` (default 24h). Cache is invalidated for a collection when new documents are ingested into it.

## Rationale

- Exact catches the cheap cases for free. ~5ms latency.
- Semantic increases hit rate materially on chat workloads. We saw 12% → 34% in the spec's example numbers; we will validate against our own logs.
- Threshold of 0.95 is conservative: low false-positive rate. Too low and we serve stale answers to subtly different questions.
- Collection-scoped invalidation prevents the classic bug of serving cached answers after the user added the doc that contradicts them.

## Consequences

- Adds embedding cost to every cache *miss* (one embed call per miss to write the index). Acceptable: embedding is local + fast.
- Semantic cache only protects within a single embedder. Switching the embedder requires invalidating semantic entries.
- We expose hit/miss as Prometheus metrics from day one (already wired in `infra/metrics.py`).

## Revisit when

- Hit-rate plateaus suggest we should also cache *retrieval* results, not just final answers.
- We add multi-tenancy and need per-tenant invalidation guarantees.
