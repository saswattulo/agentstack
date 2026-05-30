"""Async eval execution. Triggered after every /query in fire-and-forget mode."""

from __future__ import annotations

from uuid import UUID

from agentstack.core.eval.metrics import EvalInput, EvalScores
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


async def evaluate_and_persist(query_log_id: UUID, payload: EvalInput) -> EvalScores:
    """Run metrics, write EvalResult, update Prom gauges.

    TODO(week-3):
      1. await run_ragas_metrics(payload)
      2. citation_accuracy(...)
      3. Upsert EvalResult, link to query_log_id
      4. EVAL_FAITHFULNESS.set(...) etc.
    """
    logger.info("eval runner stub", query_log_id=str(query_log_id))
    return EvalScores()
