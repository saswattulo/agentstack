"""Multi-provider LLM abstraction.

Currently only Groq is wired. The interface stays provider-agnostic so future
providers (OpenAI, Anthropic) drop in behind the same `ChatClient` protocol
without touching feature code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from groq import AsyncGroq

from agentstack.config import settings
from agentstack.infra.logging import get_logger

logger = get_logger(__name__)


class ChatMessage(dict[str, Any]):
    """OpenAI-style chat message: {role, content, ...}."""


class ChatClient(Protocol):
    model: str

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]: ...


class GroqChatClient:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or settings.groq_chat_model
        key = api_key or settings.groq_api_key
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = AsyncGroq(api_key=key)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if tools:
            params["tools"] = tools
            params["tool_choice"] = kwargs.pop("tool_choice", "auto")
        params.update(kwargs)

        resp = await self._client.chat.completions.create(**params)
        return resp.model_dump()

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        params.update(kwargs)

        stream = await self._client.chat.completions.create(**params)
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


_client: ChatClient | None = None


def get_chat_client() -> ChatClient:
    global _client
    if _client is None:
        _client = GroqChatClient()
    return _client


def get_fallback_chat_client() -> ChatClient:
    return GroqChatClient(model=settings.groq_fallback_model)
