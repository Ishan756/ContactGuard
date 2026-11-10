import io

import docx
import pytest
from httpx import AsyncClient
from starlette.requests import Request

from app.core.config import Settings
from app.core.middleware import _client_key, _SlidingWindowRateLimiter
from tests.conftest import ADMIN_AUTH_HEADERS, REVIEWER_AUTH_HEADERS


def _contract_docx() -> bytes:
    document = docx.Document()
    document.add_heading("1. LIABILITY", level=1)
    document.add_paragraph("Vendor liability is limited to fees paid in the prior year.")
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


def _contract_files() -> dict:
    return {
        "file": (
            "security_contract.docx",
            _contract_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }


@pytest.mark.asyncio
async def test_document_endpoints_require_authentication(async_client: AsyncClient):
    response = await async_client.get("/api/v1/documents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_reviewer_cannot_access_another_reviewers_document(async_client: AsyncClient):
    upload = await async_client.post(
        "/api/v1/documents",
        files=_contract_files(),
        headers=REVIEWER_AUTH_HEADERS,
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["document"]["id"]

    other_reviewer = {
        "X-Reviewer-ID": "reviewer-b",
        "X-Workflow-Key": REVIEWER_AUTH_HEADERS["X-Workflow-Key"],
    }
    forbidden = await async_client.get(
        f"/api/v1/documents/{document_id}", headers=other_reviewer
    )
    assert forbidden.status_code == 403, forbidden.text

    admin = await async_client.get(
        f"/api/v1/documents/{document_id}", headers=ADMIN_AUTH_HEADERS
    )
    assert admin.status_code == 200, admin.text


@pytest.mark.asyncio
async def test_policy_management_is_admin_only(async_client: AsyncClient):
    payload = {
        "name": "Security Test Policy",
        "version": "1.0.0",
        "category": "Security",
        "text_content": "Only administrators may publish company policy.",
    }
    denied = await async_client.post(
        "/api/v1/policies", json=payload, headers=REVIEWER_AUTH_HEADERS
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_security_headers_are_emitted(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_rate_limiter_enforces_sliding_window():
    limiter = _SlidingWindowRateLimiter()
    assert limiter.check("client", limit=2, window_seconds=60)[0] is True
    assert limiter.check("client", limit=2, window_seconds=60)[0] is True
    allowed, remaining, retry_after = limiter.check(
        "client", limit=2, window_seconds=60
    )
    assert allowed is False
    assert remaining == 0
    assert retry_after >= 1


def test_rate_limit_client_key_honors_trusted_proxy_header_only_when_enabled():
    request = Request(
        {
            "type": "http",
            "headers": [(b"x-real-ip", b"203.0.113.7")],
            "client": ("172.18.0.5", 12345),
        }
    )
    assert _client_key(request, trust_proxy_headers=True) == "203.0.113.7"
    assert _client_key(request, trust_proxy_headers=False) == "172.18.0.5"


def test_production_settings_reject_unsafe_defaults():
    unsafe = Settings(_env_file=None, app_env="production")
    problems = unsafe.production_security_problems()
    assert any("APP_DEBUG" in problem for problem in problems)
    assert any("WORKFLOW_REVIEW_API_KEY" in problem for problem in problems)

    safe = Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        secret_key="s" * 48,
        workflow_review_api_key="reviewer-key-" + "r" * 40,
        admin_api_key="admin-key-" + "a" * 40,
        cors_origins=["https://contractguard.example.com"],
        rate_limit_enabled=True,
        security_headers_enabled=True,
        database_url="postgresql+asyncpg://user:strong-password@db:5432/contractguard",
    )
    assert safe.production_security_problems() == []

    default_db_password = safe.model_copy(
        update={
            "database_url": (
                "postgresql+asyncpg://user:postgres_secure_password@db:5432/contractguard"
            )
        }
    )
    assert any(
        "development default" in problem
        for problem in default_db_password.production_security_problems()
    )

    sqlite_checkpoint = safe.model_copy(
        update={"workflow_checkpoint_database_url": "sqlite:///data/checkpoints.db"}
    )
    assert any(
        "WORKFLOW_CHECKPOINT_BACKEND" in problem
        for problem in sqlite_checkpoint.production_security_problems()
    )
