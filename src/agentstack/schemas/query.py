from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    collection_id: UUID
    question: str = Field(..., min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=50)
    stream: bool = False
    conversation_id: UUID | None = None
    use_web_search: bool = True
    use_code_exec: bool = False


class Citation(BaseModel):
    index: int
    chunk_id: str
    document_id: UUID | None = None
    score: float
    preview: str


class QueryResponse(BaseModel):
    query_id: UUID
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    intent: str | None = None
    tools_used: list[str] = Field(default_factory=list)
    cache_hit: bool = False
    cache_hit_kind: str | None = None  # "exact" | "semantic" when cache_hit
    latency_ms: int | None = None
    model: str | None = None


class StreamingEvent(BaseModel):
    type: Literal["token", "tool_start", "tool_end", "citation", "final", "error"]
    data: dict | str
