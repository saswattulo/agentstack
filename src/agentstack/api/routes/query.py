"""Query endpoints.

The route is thin: it verifies ownership and resolves the conversation, then
delegates to `services.query_service`. The streaming variant is replaced in
Step 6.
"""

from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.api.errors import NotFoundError
from agentstack.models.collection import Collection
from agentstack.schemas.query import QueryRequest, QueryResponse
from agentstack.services import conversation_service, query_service

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
    return await query_service.run_query(
        payload,
        db=db,
        user_id=current.id,
        conversation_id=conversation_id,
        api_key_id=current.api_key_id,
    )


@router.post("/query/stream")
async def handle_query_stream(
    payload: QueryRequest, current: CurrentUserDep, db: DbSession
) -> StreamingResponse:
    await _verify_collection(db, payload.collection_id, current.id)
    conversation_id = await _resolve_conversation_id(payload, db, current.id)

    async def event_stream():
        import json

        async for event in query_service.stream_query(
            payload,
            db=db,
            user_id=current.id,
            conversation_id=conversation_id,
            api_key_id=current.api_key_id,
        ):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
