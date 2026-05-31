"""BM25 sparse retrieval over `chunk_metadata.content_preview`.

Cached in-process: per-collection index keyed by `(collection_id, chunk_count)`,
so a stable collection doesn't pay the rebuild cost on every query. A new
ingestion bumps the row count and invalidates automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from rank_bm25 import BM25Okapi
from sqlalchemy import func, select

from agentstack.infra.db import get_sessionmaker
from agentstack.models.chunk import ChunkMetadata


@dataclass
class SparseHit:
    chunk_id: str  # ChunkMetadata.id stringified
    qdrant_point_id: str
    score: float
    text: str


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class _Index:
    bm25: BM25Okapi
    chunk_ids: list[str]
    qdrant_point_ids: list[str]
    texts: list[str]
    count: int


_cache: dict[str, _Index] = {}


async def _load_index(collection_id: UUID | str) -> _Index | None:
    cid = str(collection_id)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = (
            await session.scalar(
                select(func.count())
                .select_from(ChunkMetadata)
                .where(ChunkMetadata.collection_id == cid)
            )
        ) or 0
        if count == 0:
            _cache.pop(cid, None)
            return None

        cached = _cache.get(cid)
        if cached is not None and cached.count == count:
            return cached

        result = await session.execute(
            select(
                ChunkMetadata.id,
                ChunkMetadata.qdrant_point_id,
                ChunkMetadata.content_preview,
            ).where(ChunkMetadata.collection_id == cid)
        )
        rows = result.all()

    chunk_ids = [str(r[0]) for r in rows]
    qdrant_point_ids = [r[1] for r in rows]
    texts = [r[2] or "" for r in rows]
    tokenized = [_tokenize(t) for t in texts]
    bm25 = BM25Okapi(tokenized) if any(tokenized) else BM25Okapi([[""]])

    index = _Index(
        bm25=bm25,
        chunk_ids=chunk_ids,
        qdrant_point_ids=qdrant_point_ids,
        texts=texts,
        count=count,
    )
    _cache[cid] = index
    return index


async def bm25_search(
    collection_id: UUID | str, query: str, top_k: int = 20
) -> list[SparseHit]:
    index = await _load_index(collection_id)
    if index is None:
        return []
    tokens = _tokenize(query)
    if not tokens:
        return []
    scores = index.bm25.get_scores(tokens)
    ranked = sorted(
        ((float(s), i) for i, s in enumerate(scores) if s > 0),
        reverse=True,
    )[:top_k]
    return [
        SparseHit(
            chunk_id=index.chunk_ids[i],
            qdrant_point_id=index.qdrant_point_ids[i],
            score=score,
            text=index.texts[i],
        )
        for score, i in ranked
    ]


def invalidate(collection_id: UUID | str) -> None:
    _cache.pop(str(collection_id), None)
