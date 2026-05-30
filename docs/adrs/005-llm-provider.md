# ADR 005 — LLM provider: Groq (today), abstraction-ready for multi-provider

- **Status:** Accepted
- **Date:** 2026-05-30

## Context

The build user has a Groq API key but not OpenAI or Anthropic. Groq:
- Runs open-weight models (Llama, Qwen, GPT-OSS) at very high throughput.
- Has no embedding endpoint — embeddings must come from somewhere else.
- Is cheap enough to use as primary, not just a fallback.

The platform's spec calls for a multi-provider abstraction (OpenAI / Anthropic / Groq) with fallback. We need to build the abstraction without building dead code for providers we cannot test.

## Decision

- **Primary LLM:** Groq, model `qwen/qwen3-32b`. Fallback: `llama-3.3-70b-versatile`.
- **Embeddings:** sentence-transformers local (`BAAI/bge-small-en-v1.5`, 384-dim). Groq cannot serve embeddings.
- **Abstraction:** `infra.llm.ChatClient` Protocol. Today only `GroqChatClient` implements it. Adding `OpenAIChatClient` or `AnthropicChatClient` later is a single-file change; feature code is provider-agnostic.

## Rationale

- One real provider beats stubs for three. The user can demo end-to-end immediately.
- The `ChatClient` Protocol enforces an OpenAI-style chat schema (`messages: list[dict]`, returns OpenAI-shape dict). Both OpenAI and Anthropic SDKs map onto this with thin adapters.
- Embeddings stay local because (a) Groq has no endpoint and (b) we avoid an API dep for the hottest path in ingestion.

## Consequences

- Token accounting differs per provider; the `infra.metrics.LLM_TOKENS` counter is labeled by `(provider, model, kind)` so we can mix.
- Tool-use format is OpenAI-compatible. Groq supports this directly. Anthropic's Tool Use will need a small translation layer if/when added.
- We deliberately *don't* install the OpenAI or Anthropic SDKs — see CLAUDE.md Don'ts. Avoids contributors reaching for them.

## Revisit when

- The user obtains OpenAI/Anthropic keys and wants real fallback behavior.
- Groq deprecates the chosen models (their model menu rotates).
