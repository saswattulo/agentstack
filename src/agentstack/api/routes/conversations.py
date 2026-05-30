from uuid import UUID

from fastapi import APIRouter, Query, status

from agentstack.api.deps import CurrentUserDep, DbSession
from agentstack.schemas.common import Pagination
from agentstack.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationMessage,
    ConversationRead,
    ConversationUpdate,
)
from agentstack.services import conversation_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate, current: CurrentUserDep, db: DbSession
) -> ConversationRead:
    conv = await conversation_service.create_conversation(
        db,
        user_id=current.id,
        title=payload.title,
        collection_id=payload.collection_id,
    )
    return ConversationRead.model_validate(conv)


@router.get("", response_model=Pagination[ConversationRead])
async def list_conversations(
    current: CurrentUserDep,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination[ConversationRead]:
    items, total = await conversation_service.list_conversations(
        db, user_id=current.id, limit=limit, offset=offset
    )
    return Pagination[ConversationRead](
        items=[ConversationRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: UUID, current: CurrentUserDep, db: DbSession
) -> ConversationDetail:
    conv = await conversation_service.get_conversation_for_user(
        db, conversation_id, current.id
    )
    messages = await conversation_service.list_messages(
        db, conversation_id=conversation_id, user_id=current.id
    )
    return ConversationDetail(
        **ConversationRead.model_validate(conv).model_dump(),
        messages=[
            ConversationMessage(
                query_id=m.id,
                question=m.question,
                answer=m.answer,
                citations=m.citations,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    current: CurrentUserDep,
    db: DbSession,
) -> ConversationRead:
    conv = await conversation_service.get_conversation_for_user(
        db, conversation_id, current.id
    )
    if payload.title is not None:
        conv.title = payload.title
    await db.commit()
    await db.refresh(conv)
    return ConversationRead.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID, current: CurrentUserDep, db: DbSession
) -> None:
    await conversation_service.delete_conversation(
        db, conversation_id=conversation_id, user_id=current.id
    )
