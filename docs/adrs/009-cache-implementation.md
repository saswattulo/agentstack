# ADR 009 — LLM cache: per-collection LRU, Redis-backed, ingestion-invalidated

- **Status:** Accepted (refines ADR-004)
- **Date:** 2026-06-02

## Context

ADR-004 sketched a two-level LLM cache (exact + semantic) but left the storage layout and invalidation contract open. Week 3 had to pick concrete shapes that:

- Stay cheap to invalidate when a collection's chunks change (otherwise stale answers leak across ingestion).
- Don't grow unbounded (semantic cache vectors are 1.5KB each; an active user could accumulate thousands).
- Fail open under Redis hiccups so a cache outage never breaks the query path.
- Don't poison the cache with context-sensitive answers (the synthesizer's output to a question like "what did you just say?" is meaningless out of conversation context).

## Decision

Three Redis namespaces, all per-collection except the exact entries which are content-addressed:

```
llmcache:exact:<sha256>            STRING  JSON CachedAnswer, TTL=CACHE_TTL_SECONDS
llmcache:vecidx:<collection_id>    HASH    cache_key → base64(float32 vector)
llmcache:lru:<collection_id>       ZSET    cache_key → ns timestamp (LRU pointer)
```

**`cache_key(question, collection_id)`** is `sha256(json({"q": question_norm, "c": collection_id}))` — already in cache.py. Normalization is `strip().lower()`.

**`get(question, collection_id)`**:

1. `GET llmcache:exact:<key>`. Hit → `CACHE_HITS{kind=exact}`, touch the LRU score, return.
2. Embed the query (local sentence-transformer), `HGETALL llmcache:vecidx:<collection_id>`, compute cosine vs every stored vector, pick the max. If max ≥ `SEMANTIC_CACHE_THRESHOLD` (default 0.95), `GET` the corresponding exact payload, touch LRU, `CACHE_HITS{kind=semantic}`, return.
3. Miss → `CACHE_MISSES`.

**`set(...)`**:

- Skip when `answer == ""` or `intent == "conversational"`.
- `SET llmcache:exact:<key> EX CACHE_TTL_SECONDS`.
- `HSET llmcache:vecidx:<collection_id> <key> <encoded vec>`; `ZADD llmcache:lru:<collection_id> <ns> <key>`.
- If `ZCARD > 200`, evict the oldest entries from all three structures.

**Invalidation** is per-collection. The Celery ingest task calls `invalidate_collection_sync(collection_id)` right after Qdrant upsert. That fans out `HKEYS vecidx`, deletes each `llmcache:exact:<k>`, then deletes the hash + zset. We use the sync redis client there to avoid spinning an event loop inside the Celery worker.

## Rationale

- **Why per-collection scoping?** A single Redis hash per collection means invalidation is `O(entries_in_collection)`, not `O(global_cache)`. Most users have <20 collections and <500 entries per collection — invalidation stays sub-millisecond. A global hash would require scanning to find the affected entries.
- **Why a separate exact namespace?** Exact entries are content-addressed (the key is the hash of the question + collection). The same question against the same collection always lands on the same key, so we get TTL-based expiry for free. The hash + zset are bookkeeping for invalidation and eviction.
- **Why `cache_max_per_collection = 200`?** Empirically: 200 × 1.5KB ≈ 300KB per collection in Redis hash storage, plus ~30KB for the LRU zset. For a user with 100 collections, the worst-case Redis footprint is ~33MB. That's comfortable. At 200 entries we still get high hit rate because the head of the LRU is the most-asked questions, which tend to repeat.
- **Why the `intent == "conversational"` skip?** The synthesizer reuses prior turns when crafting a conversational reply. Caching that reply against the standalone question would yield wrong answers when other conversations ask the same surface form.
- **Why fail-open on Redis errors?** A cache outage should slow the system, not break it. Every Redis call is wrapped in try/except → logger.exception → return as if it were a miss / no-op on writes.
- **Why semantic threshold 0.95?** Conservative. Below 0.93 we started seeing topic-bleed: "what's the vector store?" semantically matching "what's the cache strategy?" on the same project's documentation. 0.95 keeps cross-question contamination rare while still catching common paraphrases (we verified live: "what vector store" → "which vector DB" hits at ~0.97).

## Consequences

- `invalidate_collection_sync` uses `redis.from_url(settings.redis_dsn)` directly instead of going through the shared async helper. One more Redis connection per ingestion, but ingestions are rare relative to queries and we avoid the asyncio bridge inside Celery.
- Embedding the query on every cache miss is intentional — we need the vector for the next `set()` anyway. The cost is one local CPU pass through sentence-transformers (~30ms) on cache misses, which is dominated by the LLM call that follows. On cache hits, the cost is amortized away.
- The Prom gauges `EVAL_FAITHFULNESS` and `EVAL_CITATION_ACCURACY` are updated from the **Celery worker**, but `/metrics` is scraped from the **api**. Workers and api each have their own process-local Prometheus registry, so the api's `/metrics` doesn't reflect worker-side gauges. That's a known limitation of the Prom client — fixing it requires multiprocess mode with a shared filesystem dir, or pushing metrics through a pushgateway. We document this and leave it for Week 4.
- Cache hit responses skip the eval enqueue. This is the right behavior (the answer was eval'd when it was first written) and also keeps eval load proportional to *novel* queries rather than total traffic.

## Out of scope

- Cross-collection cache sharing (a question asked against collection A doesn't benefit collection B even if the doc set overlaps).
- LRU promotion based on hit rate (today's LRU is touched on hit; we could also boost score by N for frequent keys).
- A `disable_cache` per-request flag — not yet asked for.
- Cache statistics endpoint — the existing `/metrics` is enough.

## Revisit when

- Hit rate plateaus and inspection of misses shows recurring near-misses below the 0.95 threshold (consider sliding to 0.92 with a stricter LRU policy).
- Per-collection cache size becomes a memory concern (Redis MEMORY USAGE per key, push toward smaller vectors).
- We add a second embedder (the vec index is implicitly tied to one model; switching invalidates the semantic layer).
