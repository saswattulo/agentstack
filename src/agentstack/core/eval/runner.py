"""Async eval execution. Run via Celery after every non-cached `/query`."""

from __future__ import annotations

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
from agentstack.models.chunk import ChunkMetadata
from agentstack.models.eval import EvalResult, QueryLog

logger = get_logger(__name__)


async def evaluate_and_persist(query_log_id: UUID, session) -> EvalScores:
    """Run all metrics, write EvalResult, update Prom gauges."""
    log = await session.get(QueryLog, query_log_id)
    if log is None or not log.answer:
        logger.warning("eval skipped: missing log or empty answer", query_log_id=str(query_log_id))
        return EvalScores()

    citation_chunk_ids = [c.get("chunk_id") for c in (log.citations or []) if c.get("chunk_id")]
    contexts: list[str] = []
    if citation_chunk_ids:
        result = await session.execute(
            select(ChunkMetadata.qdrant_point_id, ChunkMetadata.content_preview).where(
                ChunkMetadata.qdrant_point_id.in_(citation_chunk_ids)
            )
        )
        preview_by_id = {row[0]: row[1] for row in result.all() if row[1]}
        # Preserve the order that the answer's `[n]` markers expect.
        contexts = [preview_by_id[cid] for cid in citation_chunk_ids if cid in preview_by_id]
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
    scores.citation_accuracy = citation_accuracy(payload.answer, payload.contexts, payload.citations)

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
