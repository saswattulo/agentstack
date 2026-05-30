from prometheus_client import Counter, Gauge, Histogram

# HTTP-layer metrics are handled by prometheus-fastapi-instrumentator.
# Custom domain metrics live here.

DOCUMENTS_INGESTED = Counter(
    "agentstack_documents_ingested_total",
    "Documents successfully ingested",
    labelnames=("collection_id", "source_type"),
)

INGESTION_FAILURES = Counter(
    "agentstack_ingestion_failures_total",
    "Document ingestion failures",
    labelnames=("collection_id", "stage"),
)

CHUNKS_CREATED = Counter(
    "agentstack_chunks_created_total",
    "Total chunks created during ingestion",
    labelnames=("collection_id",),
)

COLLECTIONS_TOTAL = Gauge(
    "agentstack_collections_total",
    "Number of collections currently present",
)

QUERY_LATENCY = Histogram(
    "agentstack_query_latency_seconds",
    "End-to-end /query latency in seconds",
    labelnames=("collection_id",),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
)

LLM_TOKENS = Counter(
    "agentstack_llm_tokens_total",
    "Total LLM tokens consumed",
    labelnames=("provider", "model", "kind"),  # kind = prompt|completion
)

RETRIEVAL_CHUNKS_RETURNED = Histogram(
    "agentstack_retrieval_chunks_returned",
    "Number of chunks returned from retrieval",
    buckets=(1, 3, 5, 10, 20, 50, 100),
)

CACHE_HITS = Counter(
    "agentstack_cache_hits_total",
    "LLM cache hits",
    labelnames=("kind",),  # exact | semantic
)

CACHE_MISSES = Counter(
    "agentstack_cache_misses_total",
    "LLM cache misses",
)

EVAL_FAITHFULNESS = Gauge(
    "agentstack_eval_faithfulness_score",
    "Latest faithfulness score from RAGAS",
)

EVAL_CITATION_ACCURACY = Gauge(
    "agentstack_eval_citation_accuracy",
    "Citation accuracy (custom metric)",
)
