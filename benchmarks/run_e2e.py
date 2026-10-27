"""End-to-end benchmark against the live stack: ingest → query → cache → eval → isolation → rate limit.

Run:  uv run python benchmarks/run_e2e.py --out benchmarks/results/e2e.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
CORPUS = [
    *sorted((ROOT / "docs" / "adrs").glob("*.md")),
    ROOT / "docs" / "architecture.md",
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
]


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def summarize(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 1) if values else None,
        "p50": pct(values, 50),
        "p95": pct(values, 95),
        "max": round(max(values), 1) if values else None,
    }


def mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.mean(vals), 3) if vals else None


def keywords_ok(answer: str, groups: list[list[str]]) -> bool:
    a = answer.lower()
    return all(any(k.lower() in a for k in group) for group in groups)


async def ingest(client: httpx.AsyncClient, coll_id: str) -> tuple[dict, dict[str, str]]:
    t0 = time.perf_counter()
    doc_ids: dict[str, str] = {}
    for path in CORPUS:
        with path.open("rb") as fh:
            r = await client.post(
                f"/api/v1/collections/{coll_id}/ingest",
                files={"file": (path.name, fh, "text/markdown")},
            )
        r.raise_for_status()
        doc_ids[r.json()["id"]] = path.name
    upload_s = time.perf_counter() - t0

    pending = set(doc_ids)
    docs: dict[str, dict] = {}
    while pending:
        for did in list(pending):
            d = (await client.get(f"/api/v1/documents/{did}")).json()
            if d["status"] in {"completed", "failed"}:
                docs[did] = d
                pending.discard(did)
        if pending:
            await asyncio.sleep(0.25)
        if time.perf_counter() - t0 > 600:
            raise TimeoutError(f"ingestion stuck: {pending}")
    total_s = time.perf_counter() - t0

    chunks = sum(d["chunk_count"] for d in docs.values())
    failed = [doc_ids[k] for k, d in docs.items() if d["status"] != "completed"]
    words = sum(len(p.read_text(encoding="utf-8").split()) for p in CORPUS)
    return (
        {
            "documents": len(CORPUS),
            "failed": failed,
            "words": words,
            "chunks": chunks,
            "upload_s": round(upload_s, 2),
            "end_to_end_s": round(total_s, 2),
            "chunks_per_s": round(chunks / total_s, 1),
            "docs_per_min": round(len(CORPUS) / total_s * 60, 1),
        },
        doc_ids,
    )


async def ask(client: httpx.AsyncClient, coll_id: str, question: str) -> dict:
    body = {"collection_id": coll_id, "question": question, "use_web_search": False}
    for attempt in range(4):
        t0 = time.perf_counter()
        r = await client.post("/api/v1/query", json=body)
        wall = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            return {**r.json(), "wall_ms": wall, "attempts": attempt + 1}
        await asyncio.sleep(10 * (attempt + 1))
    return {"error": r.status_code, "wall_ms": wall, "attempts": 4}


async def run_pass(client, coll_id, golden, doc_ids, *, field: str) -> list[dict]:
    rows = []
    for item in golden:
        q = item.get(field)
        if not q:
            continue
        res = await ask(client, coll_id, q)
        cited = [doc_ids.get(str(c.get("document_id")), "?") for c in res.get("citations", [])]
        rows.append(
            {
                "id": item["id"],
                "question": q,
                "error": res.get("error"),
                "query_id": res.get("query_id"),
                "cache_hit": res.get("cache_hit", False),
                "cache_hit_kind": res.get("cache_hit_kind"),
                "server_ms": res.get("latency_ms"),
                "wall_ms": round(res["wall_ms"], 1),
                "attempts": res["attempts"],
                "intent": res.get("intent"),
                "model": res.get("model"),
                "cited_docs": cited,
                "source_hit": any(c in item["sources"] for c in cited),
                "citation_precision": (
                    sum(c in item["sources"] for c in cited) / len(cited) if cited else 0.0
                ),
                "has_citation": bool(cited),
                "keywords_ok": keywords_ok(res.get("answer", ""), item["keywords"]),
                "answer": res.get("answer", ""),
            }
        )
        print(
            f"  {item['id']} {field:<10} hit={rows[-1]['cache_hit']!s:<5} "
            f"src={rows[-1]['source_hit']!s:<5} kw={rows[-1]['keywords_ok']!s:<5} "
            f"{rows[-1]['wall_ms']:.0f}ms"
        )
    return rows


async def collect_evals(client, rows: list[dict], timeout_s: int = 600) -> dict[str, dict]:
    out: dict[str, dict] = {}
    deadline = time.perf_counter() + timeout_s
    pending = {r["query_id"] for r in rows if r["query_id"] and not r["cache_hit"]}
    while pending and time.perf_counter() < deadline:
        for qid in list(pending):
            e = (await client.get(f"/api/v1/eval/results/{qid}")).json()
            if e.get("status") == "ready":
                out[qid] = e
                pending.discard(qid)
        if pending:
            await asyncio.sleep(2)
    return out


async def isolation_probe(api: str, coll_id: str, doc_id: str) -> dict:
    async with httpx.AsyncClient(base_url=api, timeout=30) as c:
        tok = (
            await c.post(
                "/api/v1/auth/register",
                json={
                    "email": f"bench-intruder-{secrets.token_hex(4)}@example.com",
                    "password": "bench-password-123",
                },
            )
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        probes = {
            "get_collection": await c.get(f"/api/v1/collections/{coll_id}"),
            "list_documents": await c.get(f"/api/v1/collections/{coll_id}/documents"),
            "get_document": await c.get(f"/api/v1/documents/{doc_id}"),
            "query_collection": await c.post(
                "/api/v1/query", json={"collection_id": coll_id, "question": "leak?"}
            ),
            "delete_document": await c.delete(f"/api/v1/documents/{doc_id}"),
        }
        codes = {k: r.status_code for k, r in probes.items()}
        listed = (await c.get("/api/v1/collections")).json()
        items = listed.get("items", listed) if isinstance(listed, dict) else listed
        return {
            "status_codes": codes,
            "blocked": sum(v in {403, 404} for v in codes.values()),
            "attempts": len(codes),
            "foreign_collections_visible": sum(str(i.get("id")) == coll_id for i in items),
        }


async def rate_limit_probe(api: str, n: int) -> dict:
    async with httpx.AsyncClient(base_url=api, timeout=30) as c:
        tok = (
            await c.post(
                "/api/v1/auth/register",
                json={
                    "email": f"bench-rl-{secrets.token_hex(4)}@example.com",
                    "password": "bench-password-123",
                },
            )
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        codes = [(await c.get("/api/v1/collections")).status_code for _ in range(n)]
        first_429 = next((i + 1 for i, s in enumerate(codes) if s == 429), None)
        return {
            "requests": n,
            "ok": codes.count(200),
            "throttled": codes.count(429),
            "first_429_at": first_429,
        }


def pass_stats(rows: list[dict]) -> dict:
    ok = [r for r in rows if not r["error"]]
    return {
        "n": len(rows),
        "errors": len(rows) - len(ok),
        "cache_hits": sum(r["cache_hit"] for r in ok),
        "cache_hit_kinds": {
            k: sum(r["cache_hit_kind"] == k for r in ok) for k in ("exact", "semantic")
        },
        "wall_ms": summarize([r["wall_ms"] for r in ok if r["attempts"] == 1]),
        "server_ms": summarize(
            [r["server_ms"] for r in ok if r["server_ms"] is not None and r["attempts"] == 1]
        ),
        "retried": sum(r["attempts"] > 1 for r in ok),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=os.environ.get("AGENTSTACK_API_URL", "http://localhost:8000"))
    ap.add_argument("--key", default=os.environ.get("DEV_API_KEY"))
    ap.add_argument("--golden", default=str(ROOT / "benchmarks" / "golden_docs.json"))
    ap.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "e2e.json"))
    ap.add_argument("--keep", action="store_true", help="keep the bench collection afterwards")
    args = ap.parse_args()
    golden = json.loads(Path(args.golden).read_text())

    async with httpx.AsyncClient(
        base_url=args.api, timeout=180, headers={"X-API-Key": args.key}
    ) as client:
        coll = (
            await client.post(
                "/api/v1/collections",
                json={
                    "name": f"bench-docs-{secrets.token_hex(3)}",
                    "description": "benchmark corpus",
                },
            )
        ).json()
        coll_id = coll["id"]
        print(f"collection {coll_id}")

        print("ingesting…")
        ingestion, doc_ids = await ingest(client, coll_id)
        print(json.dumps(ingestion))

        print("pass 1: cold queries")
        cold = await run_pass(client, coll_id, golden, doc_ids, field="question")
        print("pass 2: exact replay")
        exact = await run_pass(client, coll_id, golden, doc_ids, field="question")
        print("pass 3: paraphrases")
        para = await run_pass(client, coll_id, golden, doc_ids, field="paraphrase")

        print("waiting for eval worker…")
        evals = await collect_evals(client, cold)
        for r in cold:
            r["eval"] = evals.get(r["query_id"])

        isolation = await isolation_probe(args.api, coll_id, next(iter(doc_ids)))
        rate_limit = await rate_limit_probe(args.api, 75)

        if not args.keep:
            await client.delete(f"/api/v1/collections/{coll_id}")

    cold_ok = [r for r in cold if not r["error"] and not r["cache_hit"]]
    ev = [r["eval"] for r in cold_ok if r.get("eval")]
    results = {
        "collection_id": coll_id,
        "golden_size": len(golden),
        "ingestion": ingestion,
        "quality": {
            "n": len(cold_ok),
            "source_hit_rate": mean([float(r["source_hit"]) for r in cold_ok]),
            "citation_precision": mean([r["citation_precision"] for r in cold_ok]),
            "answers_with_citations": mean([float(r["has_citation"]) for r in cold_ok]),
            "keyword_accuracy": mean([float(r["keywords_ok"]) for r in cold_ok]),
            "eval_coverage": round(len(ev) / len(cold_ok), 3) if cold_ok else None,
            "faithfulness": mean([e.get("faithfulness") for e in ev]),
            "faithfulness_scored": sum(e.get("faithfulness") is not None for e in ev),
            "answer_relevancy": mean([e.get("answer_relevancy") for e in ev]),
            "citation_accuracy": mean([e.get("citation_accuracy") for e in ev]),
        },
        "cold": pass_stats(cold),
        "exact_replay": pass_stats(exact),
        "paraphrase": pass_stats(para),
        "semantic_false_positives_on_cold_pass": sum(r["cache_hit"] for r in cold),
        "isolation": isolation,
        "rate_limit": rate_limit,
        "rows": {"cold": cold, "exact": exact, "paraphrase": para},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps({k: v for k, v in results.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
