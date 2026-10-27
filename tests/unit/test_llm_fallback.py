"""FallbackChatClient: reroute on capacity/availability errors, never on auth errors or mid-stream."""

from unittest.mock import AsyncMock, MagicMock

import groq
import httpx
import pytest

from agentstack.infra.llm import FallbackChatClient, LLMUnavailableError


def _err(cls, status: int):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=req), body=None)


def _client(model: str) -> MagicMock:
    c = MagicMock()
    c.model = model
    c.complete = AsyncMock(return_value={"model": model, "choices": []})
    return c


def _stream(*tokens, fail_after: Exception | None = None):
    async def gen(*_args, **_kwargs):
        for t in tokens:
            yield t
        if fail_after is not None:
            raise fail_after

    return gen


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cls", "status"),
    [(groq.RateLimitError, 429), (groq.NotFoundError, 404), (groq.InternalServerError, 503)],
)
async def test_complete_falls_back_on_capacity_errors(cls, status):
    primary, fallback = _client("primary"), _client("fallback")
    primary.complete.side_effect = _err(cls, status)
    resp = await FallbackChatClient(primary, fallback).complete([{"role": "user", "content": "hi"}])
    assert resp["model"] == "fallback"
    fallback.complete.assert_awaited_once()


@pytest.mark.unit
async def test_complete_does_not_fall_back_on_auth_error():
    primary, fallback = _client("primary"), _client("fallback")
    primary.complete.side_effect = _err(groq.AuthenticationError, 401)
    with pytest.raises(groq.AuthenticationError):
        await FallbackChatClient(primary, fallback).complete([])
    fallback.complete.assert_not_awaited()


@pytest.mark.unit
async def test_stream_falls_back_before_first_token():
    primary, fallback = _client("primary"), _client("fallback")
    primary.stream = _stream(fail_after=_err(groq.RateLimitError, 429))
    fallback.stream = _stream("from ", "fallback")
    tokens = [t async for t in FallbackChatClient(primary, fallback).stream([])]
    assert tokens == ["from ", "fallback"]


@pytest.mark.unit
async def test_stream_reraises_after_tokens_were_sent():
    primary, fallback = _client("primary"), _client("fallback")
    primary.stream = _stream("partial", fail_after=_err(groq.RateLimitError, 429))
    fallback.stream = _stream("never")
    seen = []
    with pytest.raises(groq.RateLimitError):
        async for t in FallbackChatClient(primary, fallback).stream([]):
            seen.append(t)
    assert seen == ["partial"]


@pytest.mark.unit
async def test_stream_success_does_not_touch_fallback():
    primary, fallback = _client("primary"), _client("fallback")
    primary.stream = _stream("a", "b")
    fallback.stream = MagicMock()
    tokens = [t async for t in FallbackChatClient(primary, fallback).stream([])]
    assert tokens == ["a", "b"]
    fallback.stream.assert_not_called()


@pytest.mark.unit
async def test_both_models_exhausted_raises_unavailable():
    primary, fallback = _client("primary"), _client("fallback")
    primary.complete.side_effect = _err(groq.RateLimitError, 429)
    fallback.complete.side_effect = _err(groq.RateLimitError, 429)
    with pytest.raises(LLMUnavailableError):
        await FallbackChatClient(primary, fallback).complete([])
