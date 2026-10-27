"""Async eval execution. Run via Celery after every non-cached `/query`."""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from agentstack.core.eval.metrics import (
    EvalInput,
    EvalScores,
    citation_accuracy,
    run_ragas_metrics,
)
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import EVAL_CITATION_ACCURACY, EVAL_FAITHFULNESS
from agentstack.infra.vectorstore import collection_name, get_qdrant_sync
from agentstack.models.chunk import ChunkMetadata
from agentstack.models.eval import EvalResult, QueryLog

logger = get_logger(__name__)


async def _chunk_texts(collection_id, point_ids: list[str], session) -> dict[str, str]:
    """Full chunk text from Qdrant; content_preview (240 chars) only where Qdrant has no text."""
    result = await session.execute(
        select(ChunkMetadata.qdrant_point_id, ChunkMetadata.content_preview).where(
            ChunkMetadata.qdrant_point_id.in_(point_ids)
        )
    )
    texts = {row[0]: row[1] for row in result.all() if row[1]}
    if collection_id is None:
        return texts
    try:
        # Sync client in a thread: each Celery eval runs in a fresh event loop.
        points = await asyncio.to_thread(
            get_qdrant_sync().retrieve,
            collection_name(str(collection_id)),
            ids=point_ids,
            with_payload=True,
        )
    except Exception:
        logger.exception("eval: qdrant chunk fetch failed, using previews")
        return texts
    for p in points:
        text = str((p.payload or {}).get("text") or "")
        if text:
            texts[str(p.id)] = text
    return texts


async def evaluate_and_persist(query_log_id: UUID, session) -> EvalScores:
    """Run all metrics, write EvalResult, update Prom gauges."""
    log = await session.get(QueryLog, query_log_id)
    if log is None or not log.answer:
        logger.warning("eval skipped: missing log or empty answer", query_log_id=str(query_log_id))
        return EvalScores()

    citations = [c for c in (log.citations or []) if c.get("chunk_id")]
    citation_chunk_ids = [c["chunk_id"] for c in citations]
    contexts: list[str] = []
    # by_index[n-1] is the chunk behind marker [n]; markers index the retrieved top-k, not the cited list.
    by_index: list[str] = []
    if citation_chunk_ids:
        text_by_id = await _chunk_texts(log.collection_id, citation_chunk_ids, session)
        contexts = [text_by_id[cid] for cid in citation_chunk_ids if cid in text_by_id]
        by_index = [""] * max(int(c.get("index") or 0) for c in citations)
        for c in citations:
            if c.get("index"):
                by_index[int(c["index"]) - 1] = text_by_id.get(c["chunk_id"], "")
    if not contexts and log.collection_id:
        result = await session.execute(
            select(ChunkMetadata.content_preview)
            .where(ChunkMetadata.collection_id == log.collection_id)
            .limit(20)
        )
        contexts = [row[0] for row in result.all() if row[0]]

    payload = EvalInput(
        question=log.question,
        answer=log.answer or "",
        contexts=contexts,
        citations=list(log.citations or []),
    )

    scores = await run_ragas_metrics(payload)
    scores.citation_accuracy = citation_accuracy(
        payload.answer, by_index or payload.contexts, payload.citations
    )

    session.add(
        EvalResult(
            query_log_id=query_log_id,
            faithfulness=scores.faithfulness,
            answer_relevancy=scores.answer_relevancy,
            context_precision=None,
            context_recall=None,
            citation_accuracy=scores.citation_accuracy,
            metrics_extra={"contexts_n": len(contexts)},
        )
    )
    await session.commit()

    if scores.faithfulness is not None:
        EVAL_FAITHFULNESS.set(float(scores.faithfulness))
    if scores.citation_accuracy is not None:
        EVAL_CITATION_ACCURACY.set(float(scores.citation_accuracy))

    logger.info(
        "eval completed",
        query_log_id=str(query_log_id),
        faithfulness=scores.faithfulness,
        answer_relevancy=scores.answer_relevancy,
        citation_accuracy=scores.citation_accuracy,
    )
    return scores
