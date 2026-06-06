"""Eval endpoints — Week 3 work. Stubbed routes so the contract is visible."""

from uuid import UUID

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import NotFoundError
from agentstack.models.eval import EvalResult, QueryLog

router = APIRouter(prefix="/api/v1/eval", tags=["eval"])


async def _get_owned_query_log(
    db: DbSession, query_id: UUID, user_id: UUID
) -> QueryLog:
    result = await db.execute(
        select(QueryLog).where(QueryLog.id == query_id, QueryLog.user_id == user_id)
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise NotFoundError("Query log not found")
    return log


@router.get("/results/{query_id}")
async def get_eval_result(
    query_id: UUID, current: CurrentUserDep, db: DbSession
) -> dict:
    """Return the eval scores for a query.

    Eval runs asynchronously on the worker, so a result may not exist yet.
    That's a normal transient state, not an error — we return 200 with
    `status: "pending"` so polling clients don't spam 404s. A genuinely
    unknown/unauthorized query_id still 404s via _get_owned_query_log.
    """
    await _get_owned_query_log(db, query_id, current.id)
    result = await db.execute(
        select(EvalResult).where(EvalResult.query_log_id == query_id)
    )
    eval_row = result.scalar_one_or_none()
    if eval_row is None:
        return {"query_id": str(query_id), "status": "pending"}
    return {
        "query_id": str(query_id),
        "status": "ready",
        "faithfulness": eval_row.faithfulness,
        "answer_relevancy": eval_row.answer_relevancy,
        "context_precision": eval_row.context_precision,
        "context_recall": eval_row.context_recall,
        "citation_accuracy": eval_row.citation_accuracy,
        "extra": eval_row.metrics_extra,
    }


@router.post("/runs/{query_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_eval(
    query_id: UUID, current: CurrentUserDep, db: DbSession
) -> dict:
    await _get_owned_query_log(db, query_id, current.id)
    # TODO(week-3): enqueue Celery eval task
    return {"query_id": str(query_id), "status": "queued_stub"}


@router.get("/aggregate")
async def aggregate_metrics(
    current: CurrentUserDep,
    db: DbSession,
    window_minutes: int = Query(default=60, ge=1, le=10_080),
) -> dict:
    """Return rolling averages of eval scores for the current user. Week 3 implements."""
    # TODO(week-3): SQL agg over EvalResult joined to QueryLog within window, filtered by user
    return {
        "window_minutes": window_minutes,
        "user_id": str(current.id),
        "faithfulness_avg": None,
        "answer_relevancy_avg": None,
        "citation_accuracy_avg": None,
        "sample_size": 0,
        "note": "stub — implemented in Week 3",
    }
