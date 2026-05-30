"""Two-level LLM cache: exact (hash) + semantic (embedding cosine).

Week 3 work — interfaces ready, store methods unimplemented.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass
class CachedAnswer:
    answer: str
    citations: list[dict]
    model: str


def cache_key(question: str, collection_id: str | None) -> str:
    payload = json.dumps(
        {"q": question.strip().lower(), "c": collection_id}, sort_keys=True
    )
    return "llmcache:exact:" + hashlib.sha256(payload.encode()).hexdigest()


class LLMCache:
    """Hybrid exact + semantic cache.

    Exact path:    Redis GET on hash key.
    Semantic path: embed query, scan a Redis-stored or Qdrant-stored vector set,
                   accept if cosine similarity > settings.semantic_cache_threshold.
    """

    async def get(self, question: str, collection_id: str | None) -> CachedAnswer | None:
        # TODO(week-3): exact lookup → semantic lookup → return CachedAnswer
        return None

    async def set(
        self,
        question: str,
        collection_id: str | None,
        answer: CachedAnswer,
        ttl_seconds: int | None = None,
    ) -> None:
        # TODO(week-3): write to Redis with TTL + index for semantic lookup
        return None

    async def invalidate_collection(self, collection_id: str) -> None:
        # TODO(week-3): invalidate semantic cache entries scoped to a collection
        return None
