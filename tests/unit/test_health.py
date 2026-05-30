import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.unit
async def test_health_returns_ok():
    from agentstack.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
