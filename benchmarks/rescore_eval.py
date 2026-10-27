"""Re-score benchmark queries with the production LLM judge, paced under Groq's per-minute token quota.

Runs inside the worker container:
  docker compose cp benchmarks worker:/tmp/benchmarks
  docker compose exec worker python /tmp/benchmarks/rescore_eval.py /tmp/benchmarks/results/e2e.json
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
from pathlib import Path
from uuid import UUID

import groq

from agentstack.core.eval.metrics import citation_accuracy, faithfulness
from agentstack.infra.db import get_sessionmaker
from agentstack.infra.vectorstore import collection_name, get_qdrant
from agentstack.models.eval import QueryLog


async def with_backoff(coro_fn, *args, attempts: int = 6):
    for i in range(attempts):
        try:
            return await coro_fn(*args)
        except groq.RateLimitError:
            await asyncio.sleep(20 * (i + 1))
    return None


async def full_texts(collection_id: str, point_ids: list[str]) -> dict[str, str]:
    points = await get_qdrant().retrieve(
        collection_name(collection_id), ids=point_ids, with_payload=True
    )
    return {str(p.id): str((p.payload or {}).get("text", "")) for p in points}


async def main() -> None:
    results = json.loads(Path(sys.argv[1]).read_text())
    # "preview" scores what the production eval sees (240-char previews); "full" uses the chunk text.
    source = sys.argv[2] if len(sys.argv) > 2 else "preview"
    rows = [r for r in results["rows"]["cold"] if r["query_id"] and not r["error"]]
    out = []
    async with get_sessionmaker()() as s:
        for r in rows:
            log = await s.get(QueryLog, UUID(r["query_id"]))
            cites = log.citations or []
            text_of = {c["chunk_id"]: c.get("preview", "") for c in cites}
            if source == "full" and cites:
                text_of = await full_texts(results["collection_id"], list(text_of))
            cited_ctx = [text_of.get(c["chunk_id"], "") for c in cites]
            by_index = [""] * max((c.get("index", 0) for c in cites), default=0)
            for c in cites:
                by_index[c["index"] - 1] = text_of.get(c["chunk_id"], "")
            f = await with_backoff(faithfulness, log.answer, cited_ctx) if cited_ctx else None
            row = {
                "id": r["id"],
                "faithfulness": f,
                "citation_accuracy_current": citation_accuracy(log.answer, cited_ctx, cites),
                "citation_accuracy_index_aligned": citation_accuracy(log.answer, by_index, cites),
            }
            out.append(row)
            print(json.dumps(row), file=sys.stderr, flush=True)
            await asyncio.sleep(8)

    def avg(key):
        vals = [o[key] for o in out if o[key] is not None]
        return round(statistics.mean(vals), 3) if vals else None

    print(
        json.dumps(
            {
                "context_source": source,
                "n": len(out),
                "faithfulness_scored": sum(o["faithfulness"] is not None for o in out),
                "faithfulness": avg("faithfulness"),
                "citation_accuracy_current": avg("citation_accuracy_current"),
                "citation_accuracy_index_aligned": avg("citation_accuracy_index_aligned"),
                "rows": out,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
