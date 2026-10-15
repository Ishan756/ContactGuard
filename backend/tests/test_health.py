import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_health(async_client: AsyncClient):
    """Test that GET /health returns 200 and expected metadata."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ContractGuard"
    assert "version" in data
    assert data["docs_url"] == "/docs"
    assert "timestamp" in data
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_liveness_probe(async_client: AsyncClient):
    """Test that GET /api/v1/health/live succeeds with uptime."""
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_readiness_probe(async_client: AsyncClient):
    """Test that GET /api/v1/health/ready returns component statuses."""
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["app"] == "ContractGuard"
    assert "components" in data
    assert "api" in data["components"]
    assert data["components"]["api"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_request_id_propagation(async_client: AsyncClient):
    """Test that client-supplied X-Request-ID is preserved and returned."""
    custom_id = "test-custom-uuid-12345"
    response = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == custom_id
