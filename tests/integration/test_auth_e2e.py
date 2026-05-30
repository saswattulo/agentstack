"""End-to-end auth: register → login → me → create collection scoped to user."""

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
    return f"test-{secrets.token_hex(6)}@example.com"


@pytest.mark.integration
async def test_register_login_me_flow():
    email = _email()
    password = "correct-horse-battery-staple"
    async with httpx.AsyncClient(base_url=API_URL) as client:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": "Test User"},
        )
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        assert token

        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == email

        # login with the same credentials
        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200
        assert login.json()["user"]["email"] == email


@pytest.mark.integration
async def test_collections_are_user_scoped():
    """Two users can't see each other's collections."""
    alice_email = _email()
    bob_email = _email()
    pwd = "abc12345-strong"
    async with httpx.AsyncClient(base_url=API_URL) as client:
        a_tok = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": alice_email, "password": pwd},
            )
        ).json()["access_token"]
        b_tok = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": bob_email, "password": pwd},
            )
        ).json()["access_token"]

        a_headers = {"Authorization": f"Bearer {a_tok}"}
        b_headers = {"Authorization": f"Bearer {b_tok}"}

        created = await client.post(
            "/api/v1/collections",
            json={"name": "alice-private", "description": "for alice"},
            headers=a_headers,
        )
        assert created.status_code == 201, created.text
        cid = created.json()["id"]

        try:
            b_list = await client.get("/api/v1/collections", headers=b_headers)
            assert b_list.status_code == 200
            assert all(c["id"] != cid for c in b_list.json()["items"])

            b_get = await client.get(f"/api/v1/collections/{cid}", headers=b_headers)
            assert b_get.status_code == 404
        finally:
            await client.delete(f"/api/v1/collections/{cid}", headers=a_headers)


@pytest.mark.integration
async def test_conversation_create_and_list():
    email = _email()
    pwd = "another-strong-pass"
    async with httpx.AsyncClient(base_url=API_URL) as client:
        tok = (
            await client.post(
                "/api/v1/auth/register", json={"email": email, "password": pwd}
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        created = await client.post(
            "/api/v1/conversations",
            json={"title": "First chat"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        conv_id = created.json()["id"]

        listed = await client.get("/api/v1/conversations", headers=headers)
        assert listed.status_code == 200
        assert any(c["id"] == conv_id for c in listed.json()["items"])
