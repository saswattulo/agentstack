from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from agentstack.models.document import DocumentStatus


class IngestUrlRequest(BaseModel):
    url: HttpUrl
    metadata: dict | None = Field(default=None)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    collection_id: UUID
    source_type: str
    source_uri: str
    filename: str | None
    mime_type: str | None
    size_bytes: int | None
    status: DocumentStatus
    progress: int
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
