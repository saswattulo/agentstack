"""Two-level LLM cache: exact (hash) + semantic (embedding cosine).

Redis layout, scoped per-collection so ingestion can invalidate cheaply:

    llmcache:exact:<sha256>           JSON CachedAnswer, TTL = CACHE_TTL_SECONDS
    llmcache:vecidx:<collection_id>   HASH cache_key → base64(float32 vector)
    llmcache:lru:<collection_id>      ZSET key=cache_key, score=epoch_ns (LRU trim)

Cache writes are skipped for intent="conversational" (context-dependent).
Cache is invalidated on the collection when new chunks are ingested.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass

import numpy as np
import redis as sync_redis

from agentstack.config import settings
from agentstack.infra.logging import get_logger
from agentstack.infra.metrics import CACHE_HITS, CACHE_MISSES
from agentstack.infra.redis import get_redis

logger = get_logger(__name__)

EXACT_PREFIX = "llmcache:exact:"
VECIDX_PREFIX = "llmcache:vecidx:"
LRU_PREFIX = "llmcache:lru:"

_MAX_PER_COLLECTION = 200


@dataclass
class CachedAnswer:
    answer: str
    citations: list[dict]
    model: str
    intent: str | None = None
    # populated on retrieval (not persisted): which path served the hit
    hit_kind: str | None = None  # "exact" | "semantic"
    hit_score: float | None = None  # cosine similarity, for semantic hits


def cache_key(question: str, collection_id: str | None) -> str:
    payload = json.dumps(
        {"q": question.strip().lower(), "c": str(collection_id) if collection_id else None},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _encode_vec(vec: list[float]) -> str:
    return base64.b64encode(np.asarray(vec, dtype=np.float32).tobytes()).decode("ascii")


def _decode_vec(payload: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(payload.encode("ascii")), dtype=np.float32)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12
    return float(np.dot(a, b) / denom)


class LLMCache:
    """Hybrid exact + semantic cache."""

    async def get(self, question: str, collection_id: str | None) -> CachedAnswer | None:
        if not settings.llm_cache_enabled:
            return None

        redis = get_redis()
        key = cache_key(question, collection_id)
        full_key = EXACT_PREFIX + key

        try:
            raw = await redis.get(full_key)
        except Exception:
            logger.exception("cache exact get failed — failing open")
            return None

        if raw is not None:
            CACHE_HITS.labels(kind="exact").inc()
            if collection_id:
                await redis.zadd(LRU_PREFIX + str(collection_id), {key: time.time_ns()})
            ans = _decode_payload(raw)
            if ans is not None:
                ans.hit_kind = "exact"
            return ans

        if not collection_id:
            CACHE_MISSES.inc()
            return None

        try:
            from agentstack.core.ingestion.embedder import get_embedder

            query_vec = np.asarray(get_embedder().embed_one(question), dtype=np.float32)
            entries = await redis.hgetall(VECIDX_PREFIX + str(collection_id))
        except Exception:
            logger.exception("cache semantic lookup failed — failing open")
            CACHE_MISSES.inc()
            return None

        best_key: str | None = None
        best_sim = -1.0
        for k, encoded in entries.items():
            try:
                sim = _cosine(query_vec, _decode_vec(encoded))
            except Exception:
                continue
            if sim > best_sim:
                best_sim = sim
                best_key = k

        if best_key is not None and best_sim >= settings.semantic_cache_threshold:
            payload = await redis.get(EXACT_PREFIX + best_key)
            if payload is not None:
                CACHE_HITS.labels(kind="semantic").inc()
                await redis.zadd(LRU_PREFIX + str(collection_id), {best_key: time.time_ns()})
                ans = _decode_payload(payload)
                if ans is not None:
                    ans.hit_kind = "semantic"
                    ans.hit_score = round(best_sim, 4)
                return ans

        CACHE_MISSES.inc()
        return None

    async def set(
        self,
        question: str,
        collection_id: str | None,
        answer: CachedAnswer,
        ttl_seconds: int | None = None,
    ) -> None:
        if not settings.llm_cache_enabled:
            return
        if not answer.answer:
            return
        if answer.intent == "conversational":
            return

        redis = get_redis()
        key = cache_key(question, collection_id)
        full_key = EXACT_PREFIX + key
        ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds

        try:
            await redis.set(full_key, json.dumps(asdict(answer)), ex=ttl)
        except Exception:
            logger.exception("cache exact set failed — continuing")
            return

        if not collection_id:
            return

        try:
            from agentstack.core.ingestion.embedder import get_embedder

            vec = get_embedder().embed_one(question)
            await redis.hset(VECIDX_PREFIX + str(collection_id), key, _encode_vec(vec))
            await redis.zadd(LRU_PREFIX + str(collection_id), {key: time.time_ns()})
            await self._trim(str(collection_id))
        except Exception:
            logger.exception("cache semantic write failed — exact entry kept")

    async def _trim(self, collection_id: str) -> None:
        redis = get_redis()
        lru_key = LRU_PREFIX + collection_id
        vec_key = VECIDX_PREFIX + collection_id
        size = await redis.zcard(lru_key)
        if size <= _MAX_PER_COLLECTION:
            return
        to_evict = size - _MAX_PER_COLLECTION
        oldest = await redis.zrange(lru_key, 0, to_evict - 1)
        if not oldest:
            return
        async with redis.pipeline(transaction=False) as pipe:
            for k in oldest:
                pipe.delete(EXACT_PREFIX + k)
            pipe.hdel(vec_key, *oldest)
            pipe.zrem(lru_key, *oldest)
            await pipe.execute()

    async def invalidate_collection(self, collection_id: str) -> None:
        redis = get_redis()
        vec_key = VECIDX_PREFIX + str(collection_id)
        lru_key = LRU_PREFIX + str(collection_id)
        try:
            keys = list((await redis.hkeys(vec_key)) or [])
        except Exception:
            logger.exception("cache invalidate (async) hkeys failed")
            keys = []
        async with redis.pipeline(transaction=False) as pipe:
            for k in keys:
                pipe.delete(EXACT_PREFIX + k)
            pipe.delete(vec_key)
            pipe.delete(lru_key)
            await pipe.execute()
        logger.info("cache invalidated", collection_id=str(collection_id), keys_dropped=len(keys))


def _decode_payload(raw: str | bytes) -> CachedAnswer | None:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        return CachedAnswer(
            answer=data.get("answer", ""),
            citations=list(data.get("citations") or []),
            model=data.get("model", ""),
            intent=data.get("intent"),
        )
    except Exception:
        logger.exception("failed to decode cached payload")
        return None


# ---- sync helper for Celery worker ----

def invalidate_collection_sync(collection_id: str) -> None:
    """Called from the Celery ingest task. Uses sync redis to avoid an event loop."""
    try:
        client = sync_redis.from_url(settings.redis_dsn, decode_responses=True)
        vec_key = VECIDX_PREFIX + str(collection_id)
        lru_key = LRU_PREFIX + str(collection_id)
        keys = list(client.hkeys(vec_key) or [])
        pipe = client.pipeline(transaction=False)
        for k in keys:
            pipe.delete(EXACT_PREFIX + k)
        pipe.delete(vec_key)
        pipe.delete(lru_key)
        pipe.execute()
        logger.info("cache invalidated (sync)", collection_id=str(collection_id), keys_dropped=len(keys))
    except Exception:
        logger.exception("sync cache invalidation failed — non-fatal")
