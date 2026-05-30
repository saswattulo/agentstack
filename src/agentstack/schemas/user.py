from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    rate_limit_per_day: int = Field(default=10_000, ge=1, le=10_000_000)


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    is_active: bool
    rate_limit_per_minute: int
    rate_limit_per_day: int
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyRead):
    """Returned exactly once at creation; includes the raw key."""

    raw_key: str
