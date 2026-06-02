"""Unit tests for the sliding-window rate limiter."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentstack.api.middleware.rate_limit import (
    RateLimitMiddleware,
    _identity,
    _is_public,
)


@pytest.mark.unit
def test_public_paths_are_exempt():
    assert _is_public("/health")
    assert _is_public("/readyz")
    assert _is_public("/metrics")
    assert _is_public("/docs")
    assert _is_public("/docs/something")
    assert _is_public("/redoc")
    assert _is_public("/openapi.json")


@pytest.mark.unit
def test_protected_paths_are_not_public():
    assert not _is_public("/api/v1/query")
    assert not _is_public("/api/v1/collections")
    assert not _is_public("/api/v1/auth/me")


@pytest.mark.unit
def test_identity_prefers_user_id():
    request = MagicMock()
    request.state.user_id = uuid4()
    request.state.api_key_id = None
    assert _identity(request).startswith("user:")


@pytest.mark.unit
def test_identity_falls_back_to_api_key_then_ip():
    user_only = MagicMock(spec_set=["state"])
    user_only.state = MagicMock(spec_set=["user_id", "api_key_id"])
    user_only.state.user_id = None
    user_only.state.api_key_id = uuid4()
    assert _identity(user_only).startswith("key:")

    anon = MagicMock(spec_set=["state", "client"])
    anon.state = MagicMock(spec_set=["user_id", "api_key_id"])
    anon.state.user_id = None
    anon.state.api_key_id = None
    anon.client = MagicMock()
    anon.client.host = "10.0.0.1"
    assert _identity(anon) == "ip:10.0.0.1"


@pytest.mark.unit
async def test_admin_bypass(monkeypatch):
    mw = RateLimitMiddleware(app=MagicMock(), enabled=True)

    request = MagicMock()
    request.url.path = "/api/v1/collections"
    request.state.is_admin = True
    request.state.user_id = uuid4()

    called = AsyncMock(return_value="passed-through")
    response = await mw.dispatch(request, called)
    assert response == "passed-through"
    called.assert_awaited_once_with(request)


@pytest.mark.unit
async def test_disabled_middleware_passes_through():
    mw = RateLimitMiddleware(app=MagicMock(), enabled=False)
    request = MagicMock()
    request.url.path = "/api/v1/anything"
    called = AsyncMock(return_value="ok")
    assert await mw.dispatch(request, called) == "ok"


@pytest.mark.unit
async def test_429_when_over_limit(monkeypatch):
    """Redis pipeline returns count > limit → 429."""
    from agentstack.config import settings

    mw = RateLimitMiddleware(app=MagicMock(), enabled=True)
    request = MagicMock()
    request.url.path = "/api/v1/collections"
    request.state.user_id = uuid4()
    request.state.is_admin = False
    request.client = MagicMock(host="127.0.0.1")

    fake_pipe = AsyncMock()
    fake_pipe.execute = AsyncMock(return_value=[0, 1, settings.rate_limit_per_minute + 1, 1])

    pipeline_cm = MagicMock()
    pipeline_cm.__aenter__ = AsyncMock(return_value=fake_pipe)
    pipeline_cm.__aexit__ = AsyncMock(return_value=False)

    fake_redis = MagicMock()
    fake_redis.pipeline = MagicMock(return_value=pipeline_cm)

    with patch("agentstack.api.middleware.rate_limit.get_redis", return_value=fake_redis):
        called = AsyncMock()
        response = await mw.dispatch(request, called)
        assert response.status_code == 429
        called.assert_not_awaited()


@pytest.mark.unit
async def test_fail_open_when_redis_errors():
    mw = RateLimitMiddleware(app=MagicMock(), enabled=True)
    request = MagicMock()
    request.url.path = "/api/v1/collections"
    request.state.user_id = uuid4()
    request.state.is_admin = False
    request.client = MagicMock(host="127.0.0.1")

    def broken_redis():
        raise RuntimeError("redis down")

    with patch("agentstack.api.middleware.rate_limit.get_redis", side_effect=broken_redis):
        called = AsyncMock(return_value="passed-through")
        response = await mw.dispatch(request, called)
        assert response == "passed-through"
