"""Conversation lookup + creation, scoped to a user."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.api.errors import NotFoundError
from agentstack.models.collection import Collection
from agentstack.models.conversation import Conversation
from agentstack.models.eval import QueryLog


async def get_conversation_for_user(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise NotFoundError("Conversation not found")
    return conversation


async def create_conversation(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str = "New conversation",
    collection_id: UUID | None = None,
) -> Conversation:
    if collection_id is not None:
        collection = await db.get(Collection, collection_id)
        if collection is None or collection.owner_id != user_id:
            raise NotFoundError("Collection not found")
    conversation = Conversation(user_id=user_id, title=title, collection_id=collection_id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    db: AsyncSession,
    *,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Conversation], int]:
    total = (
        await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
        )
    ) or 0
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def list_messages(
    db: AsyncSession, *, conversation_id: UUID, user_id: UUID, limit: int = 200
) -> list[QueryLog]:
    """Return the QueryLog rows that make up a conversation, oldest first."""
    await get_conversation_for_user(db, conversation_id, user_id)
    result = await db.execute(
        select(QueryLog)
        .where(QueryLog.conversation_id == conversation_id)
        .order_by(QueryLog.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def delete_conversation(db: AsyncSession, *, conversation_id: UUID, user_id: UUID) -> None:
    conversation = await get_conversation_for_user(db, conversation_id, user_id)
    await db.delete(conversation)
    await db.commit()
