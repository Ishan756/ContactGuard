from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.mark.asyncio
async def test_evaluation_summary_reads_latest_report(async_client: AsyncClient):
    response = await async_client.get("/api/v1/evaluation/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["dataset_version"]
    assert body["generated_at"]
    assert body["mode"] in {"mock", "live"}
    assert "baseline" in body["agents"]
    assert "multi_agent" in body["agents"]
    assert "precision" in body["agents"]["multi_agent"]["findings"]
    assert "recall" in body["agents"]["baseline"]["findings"]
    assert body["limitations"]
    assert "legal correctness" in body["notice"]


@pytest.mark.asyncio
async def test_evaluation_summary_handles_missing_report(
    async_client: AsyncClient, tmp_path: Path
):
    missing = tmp_path / "does-not-exist.json"
    app.dependency_overrides[get_settings] = lambda: Settings(
        evaluation_report_path=str(missing)
    )
    try:
        response = await async_client.get("/api/v1/evaluation/summary")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "No evaluation report" in body["reason"]


@pytest.mark.asyncio
async def test_evaluation_summary_handles_malformed_report(
    async_client: AsyncClient, tmp_path: Path
):
    malformed = tmp_path / "latest.json"
    malformed.write_text("{not valid json", encoding="utf-8")
    app.dependency_overrides[get_settings] = lambda: Settings(
        evaluation_report_path=str(malformed)
    )
    try:
        response = await async_client.get("/api/v1/evaluation/summary")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "could not be read" in body["reason"]
