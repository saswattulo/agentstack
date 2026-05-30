from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=300)
    collection_id: UUID | None = None


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    collection_id: UUID | None
    title: str
    summary: str | None
    created_at: datetime
    updated_at: datetime


class ConversationMessage(BaseModel):
    """One past turn surfaced when fetching a conversation's history."""

    query_id: UUID
    question: str
    answer: str | None
    citations: list[dict] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[ConversationMessage] = Field(default_factory=list)
