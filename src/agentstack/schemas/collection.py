from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    chunking_strategy: str = Field(default="recursive", pattern="^(recursive|semantic)$")
    chunk_size: int = Field(default=512, ge=64, le=4096)
    chunk_overlap: int = Field(default=64, ge=0, le=1024)


class CollectionUpdate(BaseModel):
    description: str | None = None


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    chunking_strategy: str
    chunk_size: int
    chunk_overlap: int
    created_at: datetime
    updated_at: datetime
