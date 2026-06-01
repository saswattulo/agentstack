# ADR 007 — Retrieval strategy: hybrid dense + sparse with RRF, cached BM25, opt-in reranker

- **Status:** Accepted
- **Date:** 2026-06-01

## Context

The query path needs to retrieve relevant chunks from a per-user collection in Qdrant, with two competing pressures:

- Dense embeddings (BAAI/bge-small-en-v1.5) cover semantic similarity well but miss exact-keyword and identifier-heavy queries — common in docs, code, and named-entity questions.
- BM25 sparse retrieval covers exact match but is brittle to paraphrasing.

We also need to keep retrieval cheap: a developer running this locally should not pay GPU costs or external API calls per query.

## Decision

**Hybrid dense + sparse retrieval fused with Reciprocal Rank Fusion.** Specifically:

1. **Dense** via `AsyncQdrantClient.query_points` against the per-collection Qdrant index. Embed query with the existing local sentence-transformer; oversample to `top_k * 4`.
2. **Sparse** via BM25 over `chunk_metadata.content_preview`. The previews are already indexed in Postgres at ingestion; we tokenize and build a `BM25Okapi` index in-process. Index is cached per collection, keyed by `(collection_id, chunk_count)` — new ingestions auto-invalidate by changing the count.
3. **Reciprocal Rank Fusion** with `rrf_k=60` (industry standard, e.g. Cormack/Clarke/Buettcher 2009). Score = Σ 1 / (rrf_k + rank_i). Equal-weighted because RRF is rank-based; dense/sparse score scales never enter the math.
4. **Sparse-only backfill:** when RRF surfaces a chunk only the sparse path saw, hydrate its payload by calling `Qdrant.retrieve(ids=[...])`. This is the failure mode we hit when the dense top-k was too narrow.
5. **Optional cross-encoder reranking** (`BAAI/bge-reranker-base`) gated by `RERANKER_ENABLED=false`. When enabled, we rerank the fused top-N. Off by default because the first invocation downloads ~280MB of weights and re-scoring is CPU-bound.

## Rationale

- **Why RRF over linear score combination?** Dense cosine and BM25 scores have incompatible distributions; calibrating them via softmax/sigmoid is fragile. RRF works on ranks only — no calibration, robust across collections.
- **Why BM25 in-process vs in Qdrant sparse vectors?** Qdrant *does* support sparse vectors natively, but adding them means re-indexing every chunk and committing to a tokenization scheme at ingest time. In-process BM25 lets us iterate on tokenization (currently the simple alphanumeric regex) without rebuilding any index. The in-memory cache makes the cost negligible after the first query in a collection.
- **Why `rrf_k=60`?** Empirically robust default. Smaller k makes the fusion overly sensitive to top-ranks; larger k flattens everything. Configurable on `HybridRetriever.__init__`.
- **Why oversample by 4x?** Dense top-5 alone tends to cluster around one good chunk; oversampling to 20 then fusing gives sparse a meaningful vote in the final top-5.
- **Why reranker off by default?** Doubles latency (cross-encoder is ~100ms/pair on CPU), needs a one-time model download, and a tuned dense+sparse pipeline already gets us ~90% of the way to top-1 precision. Treat reranker as a per-collection knob, not a default.

## Consequences

- BM25 cache lives in a process-local dict. Multi-worker scenarios won't share it (each worker rebuilds on first miss). Acceptable for now; Redis-backed sparse index is a Week 3 follow-up if cold-start latency becomes an issue.
- A new chunk in an existing collection invalidates the BM25 cache implicitly via the count check — but only after the row count actually changes. If chunks are mutated in place without count change, the cache goes stale. We don't mutate today; flag for future schema changes.
- Sparse hits that miss the dense top-k force an extra Qdrant round-trip for payload backfill. Worst case adds ~10ms per query.
- The retriever depends on `chunk_metadata.qdrant_point_id` matching the actual Qdrant point id. Week 1's ingestion stored the human-readable `"doc_id__n"` string in Postgres but used a derived UUID in Qdrant; this ADR's implementation forced that consistency (one UUID, both places).

## Out of scope

- Sparse vectors in Qdrant — Week 3 if needed.
- HyDE / query expansion — pure latency cost without consistent wins on small corpora.
- Per-document filtering at retrieval time — exposed via `metadata_filter: Filter` on `HybridRetriever.retrieve()` but not yet surfaced through the API.
- Cross-collection retrieval — out of scope for the user-isolation model.

## Revisit when

- Recall on a stable eval set (Week 3 RAGAS) plateaus and the reranker shows a >5pt lift.
- Multi-worker scale-out happens — at that point sparse index belongs in Redis or a dedicated service.
- We support large (>1M chunk) collections — BM25Okapi build cost stops being negligible.
