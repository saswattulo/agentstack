"""Retrieval ablation: dense vs BM25 vs hybrid RRF vs reranked, doc-level Hit@k / MRR / latency.

Runs inside the api container so it uses the production embedder, Qdrant and BM25 code:
  docker compose cp benchmarks api:/tmp/benchmarks
  docker compose exec api python /tmp/benchmarks/retrieval_ablation.py <collection_id>
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

from rank_bm25 import BM25Okapi
from sqlalchemy import text

from agentstack.config import settings
from agentstack.core.retrieval.hybrid import HybridRetriever, reciprocal_rank_fusion
from agentstack.core.retrieval.reranker import CrossEncoderReranker
from agentstack.core.retrieval.sparse import _tokenize, bm25_search
from agentstack.infra.db import get_sessionmaker
from agentstack.infra.vectorstore import collection_name, get_qdrant

K = 5


async def doc_maps(collection_id: str) -> tuple[dict[str, str], dict[str, str]]:
    async with get_sessionmaker()() as s:
        rows = await s.execute(
            text(
                "select c.qdrant_point_id, d.id::text, d.filename from chunk_metadata c "
                "join documents d on d.id = c.document_id where c.collection_id = :cid"
            ),
            {"cid": collection_id},
        )
        point_to_file, doc_to_file = {}, {}
        for point_id, doc_id, filename in rows.all():
            point_to_file[point_id] = filename
            doc_to_file[doc_id] = filename
        return point_to_file, doc_to_file


async def full_text_bm25(collection_id: str) -> tuple[BM25Okapi, list[str]]:
    # Production BM25 indexes the 240-char content_preview; this variant indexes the full chunk text.
    ids, docs, offset = [], [], None
    while True:
        points, offset = await get_qdrant().scroll(
            collection_name(collection_id), limit=256, offset=offset, with_payload=True
        )
        for p in points:
            ids.append(str(p.id))
            docs.append(_tokenize(str((p.payload or {}).get("text", ""))))
        if offset is None:
            return BM25Okapi(docs), ids


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def score(ranked_files: list[str], sources: list[str]) -> dict:
    first = next((i for i, f in enumerate(ranked_files[:K], start=1) if f in sources), None)
    return {
        "hit1": float(first == 1),
        "hit3": float(first is not None and first <= 3),
        "hit5": float(first is not None),
        "rr": 1.0 / first if first else 0.0,
    }


async def main() -> None:
    collection_id = sys.argv[1]
    golden = json.loads((Path(__file__).parent / "golden_docs.json").read_text())
    point_to_file, _ = await doc_maps(collection_id)
    retriever = HybridRetriever()
    if os.environ.get("RERANKER_PATH"):
        settings.reranker_model = os.environ["RERANKER_PATH"]
    reranker = CrossEncoderReranker()
    bm25_full, bm25_full_ids = await full_text_bm25(collection_id)

    def bm25_full_rank(q, n):
        scores = bm25_full.get_scores(_tokenize(q))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [bm25_full_ids[i] for i in order[:n] if scores[i] > 0]

    async def sparse_full(q):
        return [point_to_file.get(pid, "?") for pid in bm25_full_rank(q, K)]

    async def hybrid_full(q):
        dense_ids = [c.chunk_id for c in await retriever._dense(collection_id, q, K * 4, None)]
        fused = reciprocal_rank_fusion([dense_ids, bm25_full_rank(q, K * 4)], rrf_k=60)
        return [point_to_file.get(pid, "?") for pid, _ in fused[:K]]

    async def dense(q):
        return [
            point_to_file.get(c.chunk_id, "?")
            for c in await retriever._dense(collection_id, q, K, None)
        ]

    async def sparse(q):
        return [
            point_to_file.get(h.qdrant_point_id, "?")
            for h in await bm25_search(collection_id, q, K)
        ]

    async def hybrid(q):
        settings.reranker_enabled = False
        return [
            point_to_file.get(c.chunk_id, "?")
            for c in await retriever.retrieve(collection_id, q, K)
        ]

    # Same semantics as production (rerank the fused top-5) but with one shared model:
    # hybrid.py builds a new CrossEncoderReranker per query, which reloads 1.1 GB each time.
    async def hybrid_rerank_top5(q):
        settings.reranker_enabled = False
        pool = await retriever.retrieve(collection_id, q, K)
        settings.reranker_enabled = True
        out = reranker.rerank(q, pool, top_k=K)
        settings.reranker_enabled = False
        return [point_to_file.get(c.chunk_id, "?") for c in out]

    async def hybrid_rerank_top20(q):
        settings.reranker_enabled = False
        pool = await retriever.retrieve(collection_id, q, 20)
        settings.reranker_enabled = True
        out = reranker.rerank(q, pool, top_k=K)
        settings.reranker_enabled = False
        return [point_to_file.get(c.chunk_id, "?") for c in out]

    methods = {
        "dense": dense,
        "bm25": sparse,
        "hybrid_rrf": hybrid,
        "bm25 (full chunk text)": sparse_full,
        "hybrid_rrf (full-text bm25)": hybrid_full,
        "hybrid_rrf+rerank (current: rerank fused top-5)": hybrid_rerank_top5,
        "hybrid_rrf+rerank (fused top-20 -> top-5)": hybrid_rerank_top20,
    }
    if "--no-rerank" in sys.argv:
        methods = {k: v for k, v in methods.items() if "rerank" not in k}

    for fn in methods.values():
        await fn("warm up the models")

    report = {"collection_id": collection_id, "k": K, "n": len(golden), "methods": {}}
    for name, fn in methods.items():
        scores, lat = [], []
        for item in golden:
            t0 = time.perf_counter()
            files = await fn(item["question"])
            lat.append((time.perf_counter() - t0) * 1000)
            scores.append(score(files, item["sources"]))
        report["methods"][name] = {
            "hit@1": round(statistics.mean(s["hit1"] for s in scores), 3),
            "hit@3": round(statistics.mean(s["hit3"] for s in scores), 3),
            "hit@5": round(statistics.mean(s["hit5"] for s in scores), 3),
            "mrr@5": round(statistics.mean(s["rr"] for s in scores), 3),
            "latency_ms_p50": pct(lat, 50),
            "latency_ms_p95": pct(lat, 95),
        }
        print(name, report["methods"][name], file=sys.stderr)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
