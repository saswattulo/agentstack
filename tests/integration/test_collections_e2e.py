"""End-to-end collection CRUD via the live stack.

Requires `make up` + `make migrate` first. Skipped if the API isn't reachable.
"""

from __future__ import annotations

import os

import httpx
import pytest

API_URL = os.environ.get("AGENTSTACK_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("DEV_API_KEY", "dev-local-key-change-me")


def _api_up() -> bool:
    try:
        r = httpx.get(f"{API_URL}/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not reachable")


@pytest.mark.integration
async def test_collection_lifecycle():
    async with httpx.AsyncClient(base_url=API_URL, headers={"X-API-Key": API_KEY}) as client:
        create = await client.post(
            "/api/v1/collections",
            json={"name": f"itest-{os.urandom(4).hex()}", "description": "integration test"},
        )
        assert create.status_code == 201, create.text
        cid = create.json()["id"]

        try:
            got = await client.get(f"/api/v1/collections/{cid}")
            assert got.status_code == 200
            assert got.json()["id"] == cid

            listed = await client.get("/api/v1/collections")
            assert listed.status_code == 200
            assert listed.json()["total"] >= 1
        finally:
            deleted = await client.delete(f"/api/v1/collections/{cid}")
            assert deleted.status_code == 204
