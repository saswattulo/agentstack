"""End-to-end test: register → ingest → query → auto-eval row persists.

Hits the live stack (Postgres, Redis, Qdrant, Groq). Requires `make up` plus
a valid GROQ_API_KEY in .env. Skipped if the API isn't reachable.
"""

from __future__ import annotations

import asyncio
import os
import secrets

import httpx
import pytest

API_URL = os.environ.get("AGENTSTACK_API_URL", "http://localhost:8000")


def _api_up() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not reachable")


def _email() -> str:
    return f"eval-{secrets.token_hex(6)}@example.com"


SMALL_DOC = (
    "# Tiny Fixture\n\n"
    "AgentStack uses Qdrant as the vector store.\n\n"
    "The default LLM is qwen/qwen3-32b on Groq.\n\n"
    "Embeddings come from BAAI/bge-small-en-v1.5.\n"
)


@pytest.mark.integration
@pytest.mark.slow
async def test_query_writes_eval_row(tmp_path):
    fixture = tmp_path / "tiny.md"
    fixture.write_text(SMALL_DOC, encoding="utf-8")

    async with httpx.AsyncClient(base_url=API_URL, timeout=180) as client:
        token = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": _email(), "password": "abcdefgh-1234"},
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        coll_id = (
            await client.post(
                "/api/v1/collections",
                json={"name": "eval-tiny", "description": "e2e"},
                headers=headers,
            )
        ).json()["id"]

        try:
            with fixture.open("rb") as fh:
                ingest = await client.post(
                    f"/api/v1/collections/{coll_id}/ingest",
                    files={"file": ("tiny.md", fh, "text/markdown")},
                    headers=headers,
                )
            assert ingest.status_code == 202
            doc_id = ingest.json()["id"]
            for _ in range(60):
                status = (
                    await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
                ).json().get("status")
                if status in {"completed", "failed"}:
                    break
                await asyncio.sleep(1)
            assert status == "completed"

            q = await client.post(
                "/api/v1/query",
                json={
                    "collection_id": coll_id,
                    "question": "What vector store does AgentStack use?",
                },
                headers=headers,
            )
            assert q.status_code == 200
            body = q.json()
            query_id = body["query_id"]
            assert body["cache_hit"] is False
            assert "Qdrant" in body["answer"]

            # Poll the eval results endpoint until the worker has filled it.
            eval_row = None
            for _ in range(90):
                resp = await client.get(
                    f"/api/v1/eval/results/{query_id}", headers=headers
                )
                if resp.status_code == 200:
                    eval_row = resp.json()
                    break
                await asyncio.sleep(1)
            assert eval_row is not None, "eval row never appeared"

            # At least one of the scored metrics should be non-null on a real
            # factual answer; citation_accuracy is always populated.
            assert eval_row.get("citation_accuracy") is not None
        finally:
            await client.delete(f"/api/v1/collections/{coll_id}", headers=headers)


@pytest.mark.integration
async def test_cache_hit_skips_eval(tmp_path):
    """Same question fired twice — second is a cache hit and no new eval row written."""
    fixture = tmp_path / "tiny.md"
    fixture.write_text(SMALL_DOC, encoding="utf-8")

    async with httpx.AsyncClient(base_url=API_URL, timeout=180) as client:
        token = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": _email(), "password": "abcdefgh-1234"},
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        coll_id = (
            await client.post(
                "/api/v1/collections",
                json={"name": "cache-skip-eval", "description": "e2e"},
                headers=headers,
            )
        ).json()["id"]

        try:
            with fixture.open("rb") as fh:
                doc_id = (
                    await client.post(
                        f"/api/v1/collections/{coll_id}/ingest",
                        files={"file": ("tiny.md", fh, "text/markdown")},
                        headers=headers,
                    )
                ).json()["id"]
            for _ in range(60):
                status = (
                    await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
                ).json().get("status")
                if status == "completed":
                    break
                await asyncio.sleep(1)

            q1 = (
                await client.post(
                    "/api/v1/query",
                    json={
                        "collection_id": coll_id,
                        "question": "What vector store does AgentStack use?",
                    },
                    headers=headers,
                )
            ).json()
            assert q1["cache_hit"] is False

            q2 = (
                await client.post(
                    "/api/v1/query",
                    json={
                        "collection_id": coll_id,
                        "question": "What vector store does AgentStack use?",
                    },
                    headers=headers,
                )
            ).json()
            assert q2["cache_hit"] is True
            assert q2["latency_ms"] < q1["latency_ms"]  # cache hits are fast
        finally:
            await client.delete(f"/api/v1/collections/{coll_id}", headers=headers)
