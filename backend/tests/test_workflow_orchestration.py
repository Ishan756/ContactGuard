import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.api.v1.endpoints.workflows import get_workflow_service
from app.core.config import get_settings
from app.core.embeddings.mock import DeterministicEmbeddingProvider
from app.core.llm.mock import MockLLMProvider
from app.core.security import ReviewerPrincipal
from app.db.models import ReviewDecisionType
from app.main import app
from app.schemas.workflow import WorkflowResumeRequest, WorkflowStartRequest
from app.services.clause.service import ClauseExtractionService
from app.services.risk.analysis import RiskAnalysisService
from app.services.risk.retrieval import PolicyRetrievalService
from app.services.risk.validation import EvidenceValidationService
from app.services.vector.qdrant_service import QdrantVectorService
from app.services.workflow.checkpointer import CheckpointManager
from app.services.workflow.nodes import WorkflowDependencies
from app.services.workflow.service import WorkflowService
from tests.conftest import TestingSessionLocal
from tests.test_risk_analysis import (
    LIABILITY_POLICY,
    LIABILITY_UNLIMITED,
    InMemoryVectorStore,
    clause_candidate,
    create_policy,
    upload_contract,
)


@pytest.fixture(autouse=True)
def mock_qdrant_service(monkeypatch):
    in_memory = InMemoryVectorStore()
    monkeypatch.setattr(QdrantVectorService, "ensure_collection", in_memory.ensure_collection)
    monkeypatch.setattr(QdrantVectorService, "upsert_points", in_memory.upsert_points)
    monkeypatch.setattr(
        QdrantVectorService, "delete_by_policy_id", in_memory.delete_by_policy_id
    )
    monkeypatch.setattr(QdrantVectorService, "search", in_memory.search)


def build_workflow_service(checkpointer, llm_provider) -> WorkflowService:
    settings = get_settings()
    retrieval = PolicyRetrievalService(
        vector_service=QdrantVectorService(settings),
        embedding_provider=DeterministicEmbeddingProvider(dimension=768),
        settings=settings,
    )
    dependencies = WorkflowDependencies(
        clause_extraction=ClauseExtractionService(
            llm_provider=llm_provider, settings=settings
        ),
        policy_retrieval=retrieval,
        risk_analysis=RiskAnalysisService(
            llm_provider=llm_provider,
            retrieval_service=retrieval,
            settings=settings,
        ),
        evidence_validation=EvidenceValidationService(settings=settings),
        session_factory=TestingSessionLocal,
    )
    return WorkflowService(
        dependencies=dependencies,
        checkpointer=checkpointer,
        settings=settings,
    )


def review_headers(reviewer_id: str = "reviewer-a") -> dict[str, str]:
    return {
        "X-Reviewer-ID": reviewer_id,
        "X-Workflow-Key": get_settings().workflow_review_api_key,
    }


async def prepare_contract(async_client: AsyncClient) -> str:
    await create_policy(
        async_client,
        "Vendor Liability Policy",
        LIABILITY_POLICY,
        category="liability",
    )
    return await upload_contract(
        async_client,
        [
            ("heading", "1. LIMITATION OF LIABILITY"),
            ("paragraph", LIABILITY_UNLIMITED),
        ],
    )


def extraction_llm() -> MockLLMProvider:
    return MockLLMProvider(
        [
            {
                "clauses": [
                    clause_candidate(
                        "liability",
                        LIABILITY_UNLIMITED,
                        "Unlimited vendor liability.",
                    )
                ]
            }
        ],
        model_name="mock-workflow-extractor",
    )


@pytest.mark.asyncio
async def test_workflow_pauses_for_approval_and_resumes_idempotently(
    async_client: AsyncClient, tmp_path: Path
):
    document_id = await prepare_contract(async_client)
    settings = get_settings()
    manager = CheckpointManager(
        settings,
        backend="sqlite",
        sqlite_path=str(tmp_path / "workflow-approval.db"),
    )
    await manager.start()
    service = build_workflow_service(manager.saver, extraction_llm())
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        start_headers = {**review_headers(), "Idempotency-Key": "start-approval-1"}
        response = await async_client.post(
            "/api/v1/workflows",
            json={"document_id": document_id, "enable_model_analysis": False},
            headers=start_headers,
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        workflow_id = workflow["workflow_id"]
        assert workflow["status"] == "awaiting_review"
        assert workflow["interrupted_node"] == "human_review"
        assert workflow["review_request"]["findings"]
        assert workflow["validation_run_id"]
        assert workflow["review_report"]["legal_action_performed"] is False
        assert any(
            event["event_type"] == "interrupted" for event in workflow["events"]
        )

        repeated = await async_client.post(
            "/api/v1/workflows",
            json={"document_id": document_id, "enable_model_analysis": False},
            headers=start_headers,
        )
        assert repeated.status_code == 201, repeated.text
        assert repeated.json()["workflow_id"] == workflow_id

        foreign = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json={"decision": "approve"},
            headers=review_headers("reviewer-b"),
        )
        assert foreign.status_code == 403, foreign.text

        resume_headers = {
            **review_headers(),
            "Idempotency-Key": "resume-approval-1",
        }
        body = {"decision": "approve", "notes": "Reviewed the liability deviation."}
        resumed = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json=body,
            headers=resume_headers,
        )
        assert resumed.status_code == 200, resumed.text
        completed = resumed.json()
        assert completed["status"] == "completed"
        assert completed["revision_count"] == 0
        assert completed["decisions"][-1]["decision"] == "approve"
        assert completed["decisions"][-1]["notes"] == "Reviewed the liability deviation."
        assert any(event["event_type"] == "completed" for event in completed["events"])

        duplicate = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json=body,
            headers=resume_headers,
        )
        assert duplicate.status_code == 200, duplicate.text
        assert len(duplicate.json()["decisions"]) == 1

        results = await async_client.get(
            f"/api/v1/workflows/{workflow_id}/results",
            headers=review_headers(),
        )
        assert results.status_code == 200, results.text
        payload = results.json()
        assert payload["human_review_complete"] is True
        assert payload["automatic_verification_complete"] is True
        assert payload["legal_action_performed"] is False
        assert payload["report"]["human_review"]["decision"] == "approve"
        assert all(finding["review_status"] == "reviewed" for finding in payload["findings"])
    finally:
        app.dependency_overrides.pop(get_workflow_service, None)
        await manager.stop()


@pytest.mark.asyncio
async def test_workflow_revision_appends_audit_trail_and_pauses_again(
    async_client: AsyncClient, tmp_path: Path
):
    document_id = await prepare_contract(async_client)
    settings = get_settings()
    manager = CheckpointManager(
        settings,
        backend="memory",
    )
    await manager.start()
    service = build_workflow_service(manager.saver, extraction_llm())
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        started = await async_client.post(
            "/api/v1/workflows",
            json={"document_id": document_id, "enable_model_analysis": False},
            headers=review_headers(),
        )
        assert started.status_code == 201, started.text
        workflow_id = started.json()["workflow_id"]

        revised = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json={
                "decision": "request_revision",
                "notes": "Please re-check the liability cap finding.",
                "revision_instructions": "Re-run analysis using the liability policy.",
                "revision_target": "analysis",
                "command_id": "revision-1",
            },
            headers={**review_headers(), "Idempotency-Key": "revision-1"},
        )
        assert revised.status_code == 200, revised.text
        after_revision = revised.json()
        assert after_revision["status"] == "awaiting_review"
        assert after_revision["revision_count"] == 1
        assert len(after_revision["decisions"]) == 1
        assert after_revision["decisions"][0]["decision"] == "request_revision"
        assert after_revision["decisions"][0]["revision_instructions"]

        approved = await async_client.post(
            f"/api/v1/workflows/{workflow_id}/resume",
            json={"decision": "approve", "notes": "Revision reviewed."},
            headers={**review_headers(), "Idempotency-Key": "approve-after-revision"},
        )
        assert approved.status_code == 200, approved.text
        final = approved.json()
        assert final["status"] == "completed"
        assert len(final["decisions"]) == 2
        assert [item["decision"] for item in final["decisions"]] == [
            "request_revision",
            "approve",
        ]
    finally:
        app.dependency_overrides.pop(get_workflow_service, None)
        await manager.stop()


@pytest.mark.asyncio
async def test_workflow_resume_survives_simulated_process_restart(
    async_client: AsyncClient, tmp_path: Path
):
    document_id = await prepare_contract(async_client)
    settings = get_settings()
    checkpoint_path = str(tmp_path / "workflow-restart.db")
    principal = ReviewerPrincipal(reviewer_id="reviewer-a")

    first_manager = CheckpointManager(
        settings, backend="sqlite", sqlite_path=checkpoint_path
    )
    await first_manager.start()
    first_service = build_workflow_service(first_manager.saver, extraction_llm())
    first_run = await first_service.start_workflow(
        WorkflowStartRequest(
            document_id=document_id, enable_model_analysis=False
        ),
        principal,
        idempotency_key="restart-start",
    )
    assert first_run.status == "awaiting_review"
    workflow_id = first_run.id
    await first_manager.stop()

    second_manager = CheckpointManager(
        settings, backend="sqlite", sqlite_path=checkpoint_path
    )
    await second_manager.start()
    second_service = build_workflow_service(
        second_manager.saver, MockLLMProvider([], model_name="mock-restarted")
    )
    try:
        restored = await second_service.get_workflow(workflow_id, principal)
        assert restored.status == "awaiting_review"
        resumed = await second_service.resume_workflow(
            workflow_id,
            WorkflowResumeRequest(
                decision=ReviewDecisionType.APPROVE,
                notes="Resumed after restart.",
                command_id="restart-approve",
            ),
            principal,
            idempotency_key="restart-approve",
        )
        assert resumed.status == "completed"
        assert resumed.decisions[-1].decision == "approve"
        assert resumed.completed_at is not None
    finally:
        await second_manager.stop()


@pytest.mark.asyncio
async def test_workflow_requires_authentication(async_client: AsyncClient):
    response = await async_client.post(
        "/api/v1/workflows",
        json={"document_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_missing_policy_evidence_pauses_for_human_review(
    async_client: AsyncClient, tmp_path: Path
):
    document_id = await upload_contract(
        async_client,
        [
            ("heading", "5. INDEMNITY"),
            (
                "paragraph",
                "The vendor shall indemnify the Company against all third-party claims.",
            ),
        ],
    )
    settings = get_settings()
    manager = CheckpointManager(settings, backend="memory")
    await manager.start()
    llm = MockLLMProvider(
        [
            {
                "clauses": [
                    clause_candidate(
                        "indemnity",
                        "The vendor shall indemnify the Company against all third-party claims.",
                        "Vendor indemnity.",
                    )
                ]
            }
        ]
    )
    service = build_workflow_service(manager.saver, llm)
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        response = await async_client.post(
            "/api/v1/workflows",
            json={
                "document_id": document_id,
                "enable_model_analysis": False,
                "max_retries": 0,
            },
            headers=review_headers(),
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        assert workflow["status"] == "awaiting_review"
        assert workflow["review_report"]["summary"]["missing_evidence"] >= 1
        assert workflow["review_request"]["validation"]["missing_evidence_count"] >= 1
        assert workflow["retry_count"] == 0
    finally:
        app.dependency_overrides.pop(get_workflow_service, None)
        await manager.stop()


@pytest.mark.asyncio
async def test_workflow_step_limit_fails_without_human_approval(
    async_client: AsyncClient, tmp_path: Path
):
    document_id = await prepare_contract(async_client)
    settings = get_settings()
    manager = CheckpointManager(settings, backend="memory")
    await manager.start()
    service = build_workflow_service(manager.saver, extraction_llm())
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        response = await async_client.post(
            "/api/v1/workflows",
            json={
                "document_id": document_id,
                "enable_model_analysis": False,
                "max_steps": 5,
            },
            headers=review_headers(),
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        assert workflow["status"] == "failed"
        assert workflow["error_code"] == "VALIDATION_ERROR"
        assert workflow["decisions"] == []
        assert workflow["review_report"]["status"] == "failed"
        assert workflow["review_report"]["legal_action_performed"] is False
    finally:
        app.dependency_overrides.pop(get_workflow_service, None)
        await manager.stop()
