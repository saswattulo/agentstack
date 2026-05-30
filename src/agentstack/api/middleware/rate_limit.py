"""Token-bucket rate limiter backed by Redis.

Week 3 will flesh this out per CLAUDE.md. The middleware is wired into the
app so it short-circuits with 429 once `enabled=True` is flipped on.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from agentstack.config import settings
from agentstack.infra.logging import get_logger
from agentstack.infra.redis import get_redis

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool = False) -> None:
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)

        key_id = getattr(request.state, "api_key_id", None) or "anon"
        bucket = f"ratelimit:{key_id}:minute"

        try:
            redis = get_redis()
            count = await redis.incr(bucket)
            if count == 1:
                await redis.expire(bucket, 60)
            if count > settings.rate_limit_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={"error": "Rate limit exceeded", "code": "rate_limited"},
                )
        except Exception:
            logger.exception("rate limiter failure — failing open")

        return await call_next(request)
