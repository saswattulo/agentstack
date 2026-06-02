"""Sliding-window-log rate limiter backed by Redis.

Key per user (or per API key, or per IP for unauthed callers).
Algorithm: ZSET scored by nanoseconds since epoch. On each request we trim
entries older than 60s, add the current timestamp, then check ZCARD against
the configured per-minute limit. Admin users bypass entirely.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agentstack.config import settings
from agentstack.infra.logging import get_logger
from agentstack.infra.redis import get_redis

logger = get_logger(__name__)

WINDOW_NS = 60 * 1_000_000_000  # 60 seconds

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
}


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return path.startswith("/docs") or path.startswith("/redoc")


def _identity(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        return f"user:{user_id}"
    key_id = getattr(request.state, "api_key_id", None)
    if key_id is not None:
        return f"key:{key_id}"
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = True) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled or _is_public(request.url.path):
            return await call_next(request)

        if getattr(request.state, "is_admin", False):
            return await call_next(request)

        identity = _identity(request)
        bucket = f"ratelimit:{identity}:m"
        now = time.time_ns()
        cutoff = now - WINDOW_NS
        member = f"{now}:{uuid.uuid4().hex[:8]}"

        try:
            redis = get_redis()
            async with redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(bucket, 0, cutoff)
                pipe.zadd(bucket, {member: now})
                pipe.zcard(bucket)
                pipe.expire(bucket, 60)
                _, _, count, _ = await pipe.execute()
        except Exception:
            logger.exception("rate limiter failure — failing open")
            return await call_next(request)

        if count > settings.rate_limit_per_minute:
            retry_after = max(1, int(WINDOW_NS / 1_000_000_000))
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": "Rate limit exceeded",
                    "code": "rate_limited",
                    "limit_per_minute": settings.rate_limit_per_minute,
                },
            )

        return await call_next(request)
