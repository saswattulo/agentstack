"""Hybrid retrieval: dense (Qdrant) + sparse (BM25) fused with Reciprocal Rank Fusion."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from qdrant_client.http.models import Filter

from agentstack.config import settings
from agentstack.core.ingestion.embedder import get_embedder
from agentstack.core.retrieval.sparse import bm25_search
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import RETRIEVAL_CHUNKS_RETURNED
from agentstack.infra.vectorstore import collection_name, get_qdrant

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text: str
    score: float
    payload: dict


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    rrf_k: int = 60,
) -> list[tuple[str, float]]:
    """Standard RRF: score(d) = Σ 1 / (rrf_k + rank_i(d)), 1-indexed ranks."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, key in enumerate(ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


class HybridRetriever:
    def __init__(
        self,
        *,
        rrf_k: int = 60,
        dense_oversample: int = 4,
        sparse_oversample: int = 4,
    ) -> None:
        self.rrf_k = rrf_k
        self.dense_oversample = dense_oversample
        self.sparse_oversample = sparse_oversample

    async def retrieve(
        self,
        collection_id: UUID | str,
        query: str,
        top_k: int = 5,
        *,
        metadata_filter: Filter | dict | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        dense_hits = await self._dense(
            collection_id, query, top_k * self.dense_oversample, metadata_filter
        )
        sparse_hits = await bm25_search(collection_id, query, top_k * self.sparse_oversample)

        dense_by_id: dict[str, RetrievedChunk] = {h.chunk_id: h for h in dense_hits}
        sparse_text_by_id: dict[str, str] = {h.qdrant_point_id: h.text for h in sparse_hits}

        dense_rank = [h.chunk_id for h in dense_hits]
        sparse_rank = [h.qdrant_point_id for h in sparse_hits]
        fused = reciprocal_rank_fusion([dense_rank, sparse_rank], rrf_k=self.rrf_k)

        ordered: list[RetrievedChunk] = []
        missing_ids: list[str] = []
        for point_id, fused_score in fused[: top_k * 2]:
            existing = dense_by_id.get(point_id)
            if existing is not None:
                existing.score = fused_score
                ordered.append(existing)
            else:
                missing_ids.append(point_id)

        if missing_ids:
            backfilled = await self._fetch_points(collection_id, missing_ids)
            score_by_id = {pid: s for pid, s in fused}
            for chunk in backfilled:
                chunk.score = score_by_id.get(chunk.chunk_id, chunk.score)
                ordered.append(chunk)
            ordered.sort(key=lambda c: c.score, reverse=True)

        for chunk in ordered:
            if not chunk.text and chunk.chunk_id in sparse_text_by_id:
                chunk.text = sparse_text_by_id[chunk.chunk_id]

        ordered = ordered[:top_k]

        if settings.reranker_enabled and ordered:
            from agentstack.core.retrieval.reranker import CrossEncoderReranker

            ordered = CrossEncoderReranker().rerank(query, ordered, top_k=top_k)

        RETRIEVAL_CHUNKS_RETURNED.observe(len(ordered))
        return ordered

    async def _dense(
        self,
        collection_id: UUID | str,
        query: str,
        limit: int,
        metadata_filter: Filter | dict | None,
    ) -> list[RetrievedChunk]:
        embedder = get_embedder()
        vector = embedder.embed_one(query)
        client = get_qdrant()
        name = collection_name(str(collection_id))
        try:
            response = await client.query_points(
                collection_name=name,
                query=vector,
                limit=limit,
                with_payload=True,
                query_filter=metadata_filter if isinstance(metadata_filter, Filter) else None,
            )
            hits = response.points
        except Exception as e:
            logger.warning("dense search failed", error=str(e), collection=name)
            return []

        out: list[RetrievedChunk] = []
        for h in hits:
            payload = dict(h.payload or {})
            out.append(
                RetrievedChunk(
                    chunk_id=str(h.id),
                    document_id=str(payload.get("document_id", "")),
                    text=str(payload.get("text", "")),
                    score=float(h.score),
                    payload=payload,
                )
            )
        return out

    async def _fetch_points(
        self,
        collection_id: UUID | str,
        point_ids: list[str],
    ) -> list[RetrievedChunk]:
        if not point_ids:
            return []
        client = get_qdrant()
        name = collection_name(str(collection_id))
        try:
            records = await client.retrieve(
                collection_name=name,
                ids=point_ids,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as e:
            logger.warning("point retrieve failed", error=str(e), n=len(point_ids))
            return []

        out: list[RetrievedChunk] = []
        for r in records:
            payload = dict(r.payload or {})
            out.append(
                RetrievedChunk(
                    chunk_id=str(r.id),
                    document_id=str(payload.get("document_id", "")),
                    text=str(payload.get("text", "")),
                    score=0.0,
                    payload=payload,
                )
            )
        return out
