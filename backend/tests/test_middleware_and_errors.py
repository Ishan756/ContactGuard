import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_404_not_found_standard_error(async_client: AsyncClient):
    """Test unmapped routes return standard centralized error schema with request ID."""
    response = await async_client.get("/non-existent-endpoint")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "request_id" in data
    assert response.headers.get("x-request-id") is not None


@pytest.mark.asyncio
async def test_request_id_generated_when_missing(async_client: AsyncClient):
    """Test middleware generates UUID4 when caller provides no X-Request-ID."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    req_id = response.headers.get("x-request-id")
    assert req_id is not None
    assert len(req_id) >= 16
    assert response.headers.get("x-response-time-ms") is not None
