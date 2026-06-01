"""Top-level query orchestration. Wraps the LangGraph agent + (Week 3) cache + eval scheduling."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.config import settings
from agentstack.core.agent.citations import extract_citations
from agentstack.core.agent.graph import get_compiled_graph
from agentstack.core.agent.nodes import (
    AgentState,
    build_synthesis_messages,
    retrieve_node,
    router_node,
    web_search_node,
)
from agentstack.core.retrieval.hybrid import RetrievedChunk
from agentstack.infra.llm import get_chat_client
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import QUERY_LATENCY
from agentstack.models.eval import QueryLog
from agentstack.schemas.query import Citation, QueryRequest, QueryResponse
from agentstack.services.conversation_service import get_recent_turns

logger = get_logger(__name__)


async def run_query(
    request: QueryRequest,
    *,
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    api_key_id: UUID | None = None,
) -> QueryResponse:
    """Orchestrate one query through agent → persistence.

    Caller (the route) is responsible for verifying collection ownership and
    resolving `conversation_id`.
    """
    start = time.perf_counter()
    query_id = uuid4()

    prior_turns: list[dict] = []
    if conversation_id is not None:
        prior_turns = await get_recent_turns(
            db, conversation_id=conversation_id, user_id=user_id, limit=5
        )

    state: AgentState = {
        "question": request.question,
        "collection_id": str(request.collection_id),
        "top_k": request.top_k,
        "use_web_search": request.use_web_search,
        "prior_turns": prior_turns,
        "tools_used": [],
    }

    try:
        result_state: AgentState = await get_compiled_graph().ainvoke(state)
    except Exception as exc:
        logger.exception("agent invocation failed")
        latency_ms = int((time.perf_counter() - start) * 1000)
        db.add(
            QueryLog(
                id=query_id,
                user_id=user_id,
                conversation_id=conversation_id,
                collection_id=request.collection_id,
                api_key_id=api_key_id,
                question=request.question,
                answer=None,
                latency_ms=latency_ms,
                model=settings.groq_chat_model,
                extra={"error": f"{exc.__class__.__name__}: {exc}"},
            )
        )
        await db.commit()
        raise

    answer = (result_state.get("answer") or "").strip()
    intent = result_state.get("intent")
    tools_used = list(result_state.get("tools_used") or [])
    citation_dicts = list(result_state.get("citations") or [])
    citations = [Citation.model_validate(c) for c in citation_dicts]
    model_used = result_state.get("model") or settings.groq_chat_model
    prompt_tokens = int(result_state.get("prompt_tokens") or 0) or None
    completion_tokens = int(result_state.get("completion_tokens") or 0) or None

    latency_ms = int((time.perf_counter() - start) * 1000)
    QUERY_LATENCY.labels(collection_id=str(request.collection_id)).observe(latency_ms / 1000)

    db.add(
        QueryLog(
            id=query_id,
            user_id=user_id,
            conversation_id=conversation_id,
            collection_id=request.collection_id,
            api_key_id=api_key_id,
            question=request.question,
            answer=answer or None,
            intent=intent,
            tools_used=tools_used,
            citations=citation_dicts,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model_used,
            cache_hit=False,
        )
    )
    await db.commit()

    return QueryResponse(
        query_id=query_id,
        answer=answer,
        citations=citations,
        intent=intent,
        tools_used=tools_used,
        cache_hit=False,
        latency_ms=latency_ms,
        model=model_used,
    )


async def stream_query(
    request: QueryRequest,
    *,
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    api_key_id: UUID | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Async generator yielding SSE-shaped events as the agent runs.

    Pipeline: router → retrieve (+ optional web fallback) → live token stream
    from the LLM → final citation envelope → QueryLog persisted at the end.
    Events conform to `schemas.query.StreamingEvent.type`.
    """
    start = time.perf_counter()
    query_id = uuid4()
    model = settings.groq_chat_model

    try:
        prior_turns: list[dict] = []
        if conversation_id is not None:
            prior_turns = await get_recent_turns(
                db, conversation_id=conversation_id, user_id=user_id, limit=5
            )

        state: AgentState = {
            "question": request.question,
            "collection_id": str(request.collection_id),
            "top_k": request.top_k,
            "use_web_search": request.use_web_search,
            "prior_turns": prior_turns,
            "tools_used": [],
        }

        state = await router_node(state)
        intent = state.get("intent")
        yield {"type": "tool_start", "data": {"name": "router", "intent": intent}}

        if intent == "web":
            yield {"type": "tool_start", "data": {"name": "web_search"}}
            state = await web_search_node(state)
            yield {"type": "tool_end", "data": {"name": "web_search", "n": len(state.get("web_results") or [])}}
        else:
            yield {"type": "tool_start", "data": {"name": "retrieve"}}
            state = await retrieve_node(state)
            chunks = state.get("retrieved") or []
            yield {"type": "tool_end", "data": {"name": "retrieve", "n": len(chunks)}}

            if not chunks and state.get("use_web_search", True) and settings.tavily_api_key:
                yield {"type": "tool_start", "data": {"name": "web_search", "reason": "no retrieval hits"}}
                state = await web_search_node(state)
                yield {"type": "tool_end", "data": {"name": "web_search", "n": len(state.get("web_results") or [])}}

        chunks_list: list[RetrievedChunk] = list(state.get("retrieved") or [])
        messages = build_synthesis_messages(state)

        client = get_chat_client()
        model = client.model
        buffer: list[str] = []
        async for token in client.stream(messages=messages, temperature=0.2, max_tokens=800):
            buffer.append(token)
            yield {"type": "token", "data": token}

        answer = "".join(buffer).strip()
        citations = extract_citations(answer, chunks_list)
        citation_dicts = [c.model_dump(mode="json") for c in citations]

        latency_ms = int((time.perf_counter() - start) * 1000)
        QUERY_LATENCY.labels(collection_id=str(request.collection_id)).observe(latency_ms / 1000)

        db.add(
            QueryLog(
                id=query_id,
                user_id=user_id,
                conversation_id=conversation_id,
                collection_id=request.collection_id,
                api_key_id=api_key_id,
                question=request.question,
                answer=answer or None,
                intent=intent,
                tools_used=list(state.get("tools_used") or []),
                citations=citation_dicts,
                latency_ms=latency_ms,
                model=model,
                cache_hit=False,
            )
        )
        await db.commit()

        yield {
            "type": "final",
            "data": {
                "query_id": str(query_id),
                "answer": answer,
                "citations": citation_dicts,
                "intent": intent,
                "tools_used": list(state.get("tools_used") or []),
                "latency_ms": latency_ms,
                "model": model,
            },
        }

    except Exception as exc:
        logger.exception("streaming query failed")
        latency_ms = int((time.perf_counter() - start) * 1000)
        try:
            db.add(
                QueryLog(
                    id=query_id,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    collection_id=request.collection_id,
                    api_key_id=api_key_id,
                    question=request.question,
                    answer=None,
                    latency_ms=latency_ms,
                    model=model,
                    extra={"error": f"{exc.__class__.__name__}: {exc}"},
                )
            )
            await db.commit()
        except Exception:
            await db.rollback()
        yield {
            "type": "error",
            "data": {"error": f"{exc.__class__.__name__}: {exc}", "query_id": str(query_id)},
        }


__all__ = ["run_query", "stream_query"]
