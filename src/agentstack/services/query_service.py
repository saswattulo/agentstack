"""Top-level query orchestration. Wraps the LangGraph agent + cache + eval scheduling.

Week 2 fills the orchestration; Week 3 wraps it with cache + post-hoc eval.
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.config import settings
from agentstack.core.agent.nodes import AgentState
from agentstack.infra.logging import get_logger
from agentstack.models.eval import QueryLog
from agentstack.schemas.query import QueryRequest, QueryResponse

logger = get_logger(__name__)


async def run_query(request: QueryRequest, db: AsyncSession) -> QueryResponse:
    """Orchestrate one query through cache → agent → persistence → eval enqueue."""
    # TODO(week-3): cache check
    # TODO(week-2): graph = get_compiled_graph(); state = await graph.ainvoke(...)

    start = time.perf_counter()
    query_id = uuid4()

    state: AgentState = AgentState(
        question=request.question,
        collection_id=str(request.collection_id),
        tools_used=[],
    )

    answer = "Query service not yet wired — see Week 2 work."
    latency_ms = int((time.perf_counter() - start) * 1000)

    db.add(
        QueryLog(
            id=query_id,
            collection_id=request.collection_id,
            question=request.question,
            answer=answer,
            latency_ms=latency_ms,
            model=settings.groq_chat_model,
        )
    )
    await db.commit()

    return QueryResponse(
        query_id=query_id,
        answer=answer,
        citations=[],
        intent=state.get("intent"),
        tools_used=state.get("tools_used", []),
        latency_ms=latency_ms,
        model=settings.groq_chat_model,
    )


__all__ = ["run_query"]
