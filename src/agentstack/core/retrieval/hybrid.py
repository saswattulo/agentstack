"""Hybrid retrieval: dense (Qdrant) + sparse (BM25) with Reciprocal Rank Fusion.

Week 2 work — interface is stubbed. The shape below is what `nodes.py` calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    score: float
    payload: dict


class HybridRetriever:
    def __init__(
        self,
        *,
        dense_weight: float = 0.6,
        sparse_weight: float = 0.4,
        rrf_k: int = 60,
    ) -> None:
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.rrf_k = rrf_k

    async def retrieve(
        self,
        collection_id: UUID | str,
        query: str,
        top_k: int = 10,
        *,
        metadata_filter: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Run dense + sparse retrieval, fuse with RRF, return top_k.

        TODO(week-2):
          1. Embed query via local embedder.
          2. Qdrant search → dense candidates.
          3. BM25 over PG chunk_metadata previews (or sparse vectors in Qdrant).
          4. Fuse with RRF: score = sum(1 / (rrf_k + rank_i)).
          5. Apply metadata_filter (collection_id, doc filters).
        """
        raise NotImplementedError("Implemented in Week 2.")
