"""Auth middleware. Accepts JWT bearer (preferred for end users) or an API key
(machine clients). Resolves both to a `user_id` and stores it on `request.state`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agentstack.infra.db import get_sessionmaker
from agentstack.infra.logging import get_logger
from agentstack.models.api_key import ApiKey
from agentstack.services.api_key_service import hash_api_key
from agentstack.services.jwt_service import InvalidTokenError, decode_access_token

logger = get_logger(__name__)

API_KEY_HEADER = "X-API-Key"
AUTH_HEADER = "Authorization"

PUBLIC_PATHS = {
    "/",
    "/health",
    "/livez",
    "/readyz",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
}


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.startswith("/docs") or path.startswith("/redoc")


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": message, "code": "unauthorized"})


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)

        auth_header = request.headers.get(AUTH_HEADER)
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            try:
                claims = decode_access_token(token)
            except InvalidTokenError as e:
                return _unauthorized(f"Invalid token: {e}")
            request.state.user_id = claims.user_id
            request.state.user_email = claims.email
            request.state.is_admin = claims.is_admin
            request.state.api_key_id = None
            request.state.auth_method = "jwt"
            return await call_next(request)

        raw_key = request.headers.get(API_KEY_HEADER)
        if raw_key:
            key_hash = hash_api_key(raw_key)
            sessionmaker = get_sessionmaker()
            async with sessionmaker() as session:
                result = await session.execute(
                    select(ApiKey)
                    .options(joinedload(ApiKey.user))
                    .where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
                )
                api_key = result.scalar_one_or_none()
                if api_key is None or api_key.user is None or not api_key.user.is_active:
                    return _unauthorized("Invalid API key")

                api_key.last_used_at = datetime.now(timezone.utc)
                await session.commit()

                request.state.user_id = api_key.user_id
                request.state.user_email = api_key.user.email
                request.state.is_admin = api_key.user.is_admin
                request.state.api_key_id = api_key.id
                request.state.auth_method = "api_key"
            return await call_next(request)

        return _unauthorized("Missing credentials: send Authorization: Bearer <jwt> or X-API-Key")
