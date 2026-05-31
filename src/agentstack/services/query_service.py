"""Top-level query orchestration. Wraps the LangGraph agent + (Week 3) cache + eval scheduling."""

from __future__ import annotations

import time
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.config import settings
from agentstack.core.agent.graph import get_compiled_graph
from agentstack.core.agent.nodes import AgentState
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import QUERY_LATENCY
from agentstack.models.eval import QueryLog
from agentstack.schemas.query import Citation, QueryRequest, QueryResponse
from agentstack.services.conversation_service import get_recent_turns

logger = get_logger(__name__)


async def run_query(
    request: QueryRequest,
    *,
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    api_key_id: UUID | None = None,
) -> QueryResponse:
    """Orchestrate one query through agent → persistence.

    Caller (the route) is responsible for verifying collection ownership and
    resolving `conversation_id`.
    """
    start = time.perf_counter()
    query_id = uuid4()

    prior_turns: list[dict] = []
    if conversation_id is not None:
        prior_turns = await get_recent_turns(
            db, conversation_id=conversation_id, user_id=user_id, limit=5
        )

    state: AgentState = {
        "question": request.question,
        "collection_id": str(request.collection_id),
        "top_k": request.top_k,
        "use_web_search": request.use_web_search,
        "prior_turns": prior_turns,
        "tools_used": [],
    }

    try:
        result_state: AgentState = await get_compiled_graph().ainvoke(state)
    except Exception as exc:
        logger.exception("agent invocation failed")
        latency_ms = int((time.perf_counter() - start) * 1000)
        db.add(
            QueryLog(
                id=query_id,
                user_id=user_id,
                conversation_id=conversation_id,
                collection_id=request.collection_id,
                api_key_id=api_key_id,
                question=request.question,
                answer=None,
                latency_ms=latency_ms,
                model=settings.groq_chat_model,
                extra={"error": f"{exc.__class__.__name__}: {exc}"},
            )
        )
        await db.commit()
        raise

    answer = (result_state.get("answer") or "").strip()
    intent = result_state.get("intent")
    tools_used = list(result_state.get("tools_used") or [])
    citation_dicts = list(result_state.get("citations") or [])
    citations = [Citation.model_validate(c) for c in citation_dicts]
    model_used = result_state.get("model") or settings.groq_chat_model
    prompt_tokens = int(result_state.get("prompt_tokens") or 0) or None
    completion_tokens = int(result_state.get("completion_tokens") or 0) or None

    latency_ms = int((time.perf_counter() - start) * 1000)
    QUERY_LATENCY.labels(collection_id=str(request.collection_id)).observe(latency_ms / 1000)

    db.add(
        QueryLog(
            id=query_id,
            user_id=user_id,
            conversation_id=conversation_id,
            collection_id=request.collection_id,
            api_key_id=api_key_id,
            question=request.question,
            answer=answer or None,
            intent=intent,
            tools_used=tools_used,
            citations=citation_dicts,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model_used,
            cache_hit=False,
        )
    )
    await db.commit()

    return QueryResponse(
        query_id=query_id,
        answer=answer,
        citations=citations,
        intent=intent,
        tools_used=tools_used,
        cache_hit=False,
        latency_ms=latency_ms,
        model=model_used,
    )


__all__ = ["run_query"]
