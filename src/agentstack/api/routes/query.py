"""Query endpoint — Week 2 will implement the LangGraph agent.

Today returns a stub but writes a real, owner-scoped QueryLog linked to a
conversation so the chat history persistence shape is exercised end-to-end.
"""

import json
import time
from uuid import UUID, uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import NotFoundError
from agentstack.config import settings
from agentstack.infra.metrics import QUERY_LATENCY
from agentstack.models.collection import Collection
from agentstack.models.eval import QueryLog
from agentstack.schemas.query import QueryRequest, QueryResponse
from agentstack.services import conversation_service

router = APIRouter(prefix="/api/v1", tags=["query"])


async def _verify_collection(
    db: DbSession, collection_id: UUID, user_id: UUID
) -> Collection:
    result = await db.execute(
        select(Collection).where(
            Collection.id == collection_id, Collection.owner_id == user_id
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found")
    return collection


async def _resolve_conversation_id(
    payload: QueryRequest, db: DbSession, user_id: UUID
) -> UUID | None:
    if payload.conversation_id is None:
        return None
    conv = await conversation_service.get_conversation_for_user(
        db, payload.conversation_id, user_id
    )
    return conv.id


@router.post("/query", response_model=QueryResponse)
async def handle_query(
    payload: QueryRequest, current: CurrentUserDep, db: DbSession
) -> QueryResponse:
    await _verify_collection(db, payload.collection_id, current.id)
    conversation_id = await _resolve_conversation_id(payload, db, current.id)

    start = time.perf_counter()
    query_id = uuid4()

    # TODO(week-2): replace with agentstack.core.agent.graph.invoke(...)
    answer = (
        "Query pipeline not yet implemented — Week 2 work. "
        "This endpoint will route through a LangGraph agent (router → retrieval → "
        "synthesis) and return a cited answer."
    )

    latency_ms = int((time.perf_counter() - start) * 1000)
    QUERY_LATENCY.labels(collection_id=str(payload.collection_id)).observe(latency_ms / 1000)

    log = QueryLog(
        id=query_id,
        user_id=current.id,
        conversation_id=conversation_id,
        collection_id=payload.collection_id,
        api_key_id=current.api_key_id,
        question=payload.question,
        answer=answer,
        latency_ms=latency_ms,
        model=settings.groq_chat_model,
    )
    db.add(log)
    await db.commit()

    return QueryResponse(
        query_id=query_id,
        answer=answer,
        citations=[],
        intent="stub",
        tools_used=[],
        cache_hit=False,
        latency_ms=latency_ms,
        model=settings.groq_chat_model,
    )


@router.post("/query/stream")
async def handle_query_stream(
    payload: QueryRequest, current: CurrentUserDep, db: DbSession
) -> StreamingResponse:
    await _verify_collection(db, payload.collection_id, current.id)
    await _resolve_conversation_id(payload, db, current.id)

    async def event_stream():
        # TODO(week-2): wire to agent.stream(...)
        chunks = [
            "Query streaming pipeline not yet implemented — Week 2 work. ",
            "Replace this with token-by-token output from the LangGraph agent.",
        ]
        for c in chunks:
            yield f"data: {json.dumps({'type': 'token', 'data': c})}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'data': {'citations': []}})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
