"""End-to-end query path: register → collection → ingest → query → assert cited answer.

Requires the live stack (`make up`) plus a valid GROQ_API_KEY. Skipped when the
API isn't reachable so plain `make test` doesn't fail in CI-without-stack.
"""

from __future__ import annotations

import os
import secrets

import httpx
import pytest

API_URL = os.environ.get("AGENTSTACK_API_URL", "http://localhost:8000")


def _api_up() -> bool:
    try:
        r = httpx.get(f"{API_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not reachable")


def _email() -> str:
    return f"qe2e-{secrets.token_hex(6)}@example.com"


SMALL_DOC = (
    "# Tiny Fixture\n\n"
    "AgentStack uses Qdrant as the vector store.\n\n"
    "Embeddings come from BAAI/bge-small-en-v1.5.\n\n"
    "The default chat model is qwen/qwen3-32b on Groq.\n"
)


@pytest.mark.integration
@pytest.mark.slow
async def test_full_query_path_returns_cited_answer(tmp_path):
    fixture_path = tmp_path / "tiny.md"
    fixture_path.write_text(SMALL_DOC, encoding="utf-8")

    async with httpx.AsyncClient(base_url=API_URL, timeout=180) as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": _email(), "password": "abcdefgh-strong-1"},
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        coll = await client.post(
            "/api/v1/collections",
            json={"name": "e2e-tiny", "description": "e2e fixture"},
            headers=headers,
        )
        assert coll.status_code == 201, coll.text
        coll_id = coll.json()["id"]

        try:
            with fixture_path.open("rb") as fh:
                ingest = await client.post(
                    f"/api/v1/collections/{coll_id}/ingest",
                    files={"file": ("tiny.md", fh, "text/markdown")},
                    headers=headers,
                )
            assert ingest.status_code == 202, ingest.text
            doc_id = ingest.json()["id"]

            for _ in range(60):
                doc = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
                status = doc.json().get("status")
                if status in {"completed", "failed"}:
                    break
                import asyncio

                await asyncio.sleep(1)
            assert status == "completed", f"ingestion did not complete: {doc.json()}"

            resp = await client.post(
                "/api/v1/query",
                json={
                    "collection_id": coll_id,
                    "question": "What vector store does AgentStack use?",
                },
                headers=headers,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["intent"] in {"factual", "analytical", "comparison"}
            assert "Qdrant" in body["answer"], body["answer"]
            assert len(body["citations"]) >= 1, body
            assert "retrieve" in body["tools_used"]
        finally:
            await client.delete(f"/api/v1/collections/{coll_id}", headers=headers)


@pytest.mark.integration
async def test_cross_tenant_isolation_still_holds():
    """A second user can't see or query the first user's collection."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=15) as client:
        a_token = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": _email(), "password": "abcdefgh-strong-1"},
            )
        ).json()["access_token"]
        b_token = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": _email(), "password": "abcdefgh-strong-1"},
            )
        ).json()["access_token"]

        a_headers = {"Authorization": f"Bearer {a_token}"}
        b_headers = {"Authorization": f"Bearer {b_token}"}

        coll = await client.post(
            "/api/v1/collections",
            json={"name": "iso-a", "description": "a"},
            headers=a_headers,
        )
        coll_id = coll.json()["id"]
        try:
            visible = await client.get(f"/api/v1/collections/{coll_id}", headers=b_headers)
            assert visible.status_code == 404

            q = await client.post(
                "/api/v1/query",
                json={"collection_id": coll_id, "question": "hi"},
                headers=b_headers,
            )
            assert q.status_code == 404
        finally:
            await client.delete(f"/api/v1/collections/{coll_id}", headers=a_headers)
