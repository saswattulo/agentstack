# ADR 001 — Vector store: Qdrant

- **Status:** Accepted
- **Date:** 2026-05-30

## Context

We need a vector store that:
1. Supports hybrid retrieval (dense + sparse) without external glue.
2. Has a persistent, scalable disk-backed mode (not "load everything to RAM at startup").
3. Has a usable dashboard for inspection during dev.
4. Runs in a single Docker container.
5. Is open source.

Candidates considered: Chroma, Weaviate, Milvus, Qdrant, pgvector.

## Decision

Use **Qdrant** (self-hosted via `qdrant/qdrant:v1.12.5`).

## Rationale

| Criterion | Chroma | pgvector | Milvus | Weaviate | Qdrant |
|---|---|---|---|---|---|
| Hybrid (dense+sparse) | ✗ | partial | ✓ | ✓ | ✓ |
| Single container | ✓ | (in PG) | ✗ (etcd+pulsar) | ✓ | ✓ |
| Disk-backed persistence | trial | ✓ | ✓ | ✓ | ✓ |
| Dashboard UI | ✗ | ✗ | partial | ✓ | ✓ |
| Production track record | weak | strong | strong | strong | strong |
| Resource footprint | low | low | high | medium | low |

Chroma is the easiest path but reads as a tutorial choice. Milvus is overkill for a single-machine project. pgvector inside our existing Postgres is tempting but its hybrid story (BM25 via `pgroonga`/`tsvector`) is patchier than Qdrant's native sparse vectors. Weaviate is the closest competitor; we picked Qdrant for the simpler Compose footprint and tighter Python client.

## Consequences

- Adds one Docker service + one volume.
- Qdrant collections must be created with an explicit vector dim; switching the embedder requires a rebuild.
- Hybrid search uses Qdrant's native sparse vector support (Week 2 work).

## Revisit when

- We need cross-region replication (likely move to Milvus or a managed service).
- We outgrow single-node performance and want a managed offering.
