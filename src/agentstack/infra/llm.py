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
from agentstack.infra.tracing import (
    INPUT_VALUE,
    LLM_COMPLETION_TOKENS,
    LLM_MODEL,
    LLM_PARAMS,
    LLM_PROMPT_TOKENS,
    LLM_PROVIDER,
    LLM_TOTAL_TOKENS,
    OUTPUT_VALUE,
    SPAN_KIND,
    get_tracer,
    set_attrs,
    truncate,
)

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

        tracer = get_tracer()
        with tracer.start_as_current_span("llm.complete") as span:
            set_attrs(
                span,
                **{
                    SPAN_KIND: "LLM",
                    LLM_PROVIDER: "groq",
                    LLM_MODEL: self.model,
                    LLM_PARAMS: {"temperature": temperature, "max_tokens": max_tokens},
                    INPUT_VALUE: truncate(messages),
                },
            )
            resp = await self._client.chat.completions.create(**params)
            data = resp.model_dump()

            usage = data.get("usage") or {}
            choices = data.get("choices") or [{}]
            content = (choices[0].get("message") or {}).get("content") or ""
            set_attrs(
                span,
                **{
                    LLM_PROMPT_TOKENS: int(usage.get("prompt_tokens", 0) or 0),
                    LLM_COMPLETION_TOKENS: int(usage.get("completion_tokens", 0) or 0),
                    LLM_TOTAL_TOKENS: int(usage.get("total_tokens", 0) or 0),
                    OUTPUT_VALUE: truncate(content),
                },
            )
            return data

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

        tracer = get_tracer()
        with tracer.start_as_current_span("llm.stream") as span:
            set_attrs(
                span,
                **{
                    SPAN_KIND: "LLM",
                    LLM_PROVIDER: "groq",
                    LLM_MODEL: self.model,
                    LLM_PARAMS: {"temperature": temperature, "max_tokens": max_tokens, "stream": True},
                    INPUT_VALUE: truncate(messages),
                },
            )
            stream = await self._client.chat.completions.create(**params)
            buf: list[str] = []
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    buf.append(delta)
                    yield delta
            set_attrs(span, **{OUTPUT_VALUE: truncate("".join(buf))})


_client: ChatClient | None = None


def get_chat_client() -> ChatClient:
    global _client
    if _client is None:
        _client = GroqChatClient()
    return _client


def get_fallback_chat_client() -> ChatClient:
    return GroqChatClient(model=settings.groq_fallback_model)
