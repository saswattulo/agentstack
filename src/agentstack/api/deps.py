from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.api.errors import UnauthorizedError
from agentstack.infra.db import get_session


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


RequestId = Annotated[str, Depends(get_request_id)]


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str
    is_admin: bool
    api_key_id: UUID | None
    auth_method: str


def get_current_user(request: Request) -> CurrentUser:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise UnauthorizedError("Authentication required")
    return CurrentUser(
        id=user_id,
        email=getattr(request.state, "user_email", ""),
        is_admin=bool(getattr(request.state, "is_admin", False)),
        api_key_id=getattr(request.state, "api_key_id", None),
        auth_method=getattr(request.state, "auth_method", "unknown"),
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        raise UnauthorizedError("Admin privileges required")
    return user


AdminUserDep = Annotated[CurrentUser, Depends(require_admin)]
