from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    services: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    code: str
    request_id: str | None = None
    details: dict | None = None


class Pagination(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
