import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import ProviderTimeoutError
from app.db.models import RiskFinding
from app.services.risk.validation import EvidenceValidationService
from app.services.vector.qdrant_service import QdrantVectorService
from tests.test_risk_analysis import (
    LIABILITY_POLICY,
    LIABILITY_UNLIMITED,
    InMemoryVectorStore,
    analyze_risk,
    clause_candidate,
    create_policy,
    extract_clauses,
    retrieve_policies,
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


async def create_liability_analysis(async_client: AsyncClient) -> dict:
    await create_policy(
        async_client,
        "Vendor Liability Policy",
        LIABILITY_POLICY,
        category="liability",
    )
    document_id = await upload_contract(
        async_client,
        [
            ("heading", "1. LIMITATION OF LIABILITY"),
            ("paragraph", LIABILITY_UNLIMITED),
        ],
    )
    await extract_clauses(
        async_client,
        document_id,
        [clause_candidate("liability", LIABILITY_UNLIMITED, "Unlimited vendor liability.")],
    )
    await retrieve_policies(async_client, document_id)
    return await analyze_risk(async_client, document_id)


async def tamper_finding(db_session, analysis_run_id: str, **fields) -> str:
    finding = (
        await db_session.execute(
            select(RiskFinding).where(RiskFinding.analysis_run_id == analysis_run_id)
        )
    ).scalars().first()
    assert finding is not None
    for name, value in fields.items():
        setattr(finding, name, value)
    finding.validation_status = "pending"
    finding.validation_attempts = 0
    finding.validation_error_categories = None
    finding.last_validated_at = None
    await db_session.commit()
    return finding.id


async def validate_findings(
    async_client: AsyncClient,
    document_id: str,
    analysis_run_id: str,
    max_retries: int = 0,
) -> dict:
    response = await async_client.post(
        f"/api/v1/documents/{document_id}/validate-findings",
        json={"analysis_run_id": analysis_run_id, "max_retries": max_retries},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_supported_finding_is_independently_verified(async_client: AsyncClient):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    finding = next(
        item for item in analysis["findings"] if item["rule_id"] == "liability_unlimited"
    )

    assert finding["validation_status"] == "verified"
    assert finding["validation_attempts"] >= 1
    assert finding["validation_error_categories"] == []
    assert finding["last_validated_at"]
    assert finding["contract_page_number"] == 1

    runs = await async_client.get(
        f"/api/v1/documents/{document_id}/validation-runs"
    )
    assert runs.status_code == 200
    assert runs.json()["total"] >= 1

    detail = await async_client.get(
        f"/api/v1/documents/{document_id}/validation-runs/"
        f"{runs.json()['runs'][0]['validation_run_id']}"
    )
    assert detail.status_code == 200
    attempt = detail.json()["attempts"][0]
    assert attempt["outcome"] == "verified"
    assert attempt["finding_id"] == finding["finding_id"]
    assert attempt["stage"] == "initial"


@pytest.mark.asyncio
async def test_fabricated_contract_quote_is_unverified(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(
        db_session,
        run_id,
        contract_quote="This sentence was never present in the contract.",
    )

    validation = await validate_findings(async_client, document_id, run_id)
    finding = next(item for item in validation["findings"] if item["rule_id"] == "liability_unlimited")
    assert finding["validation_status"] == "unverified"
    assert "contract_quote_not_found" in finding["validation_error_categories"]
    assert finding["review_status"] == "needs_review"
    assert validation["run"]["status"] == "partial"
    assert validation["run"]["unverified_count"] == 1


@pytest.mark.asyncio
async def test_mismatched_page_number_is_detected(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(db_session, run_id, contract_page_number=99)

    validation = await validate_findings(async_client, document_id, run_id)
    finding = next(item for item in validation["findings"] if item["rule_id"] == "liability_unlimited")
    assert finding["validation_status"] == "unverified"
    assert "page_number_mismatch" in finding["validation_error_categories"]


@pytest.mark.asyncio
async def test_wrong_policy_version_is_detected(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(db_session, run_id, policy_version="9.9.9")

    validation = await validate_findings(async_client, document_id, run_id)
    finding = next(item for item in validation["findings"] if item["rule_id"] == "liability_unlimited")
    assert finding["validation_status"] == "unverified"
    assert "policy_version_mismatch" in finding["validation_error_categories"]


@pytest.mark.asyncio
async def test_unsupported_explanation_is_detected(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(
        db_session,
        run_id,
        explanation="A purple elephant owns the moon and all of its craters.",
    )

    validation = await validate_findings(async_client, document_id, run_id)
    finding = next(item for item in validation["findings"] if item["rule_id"] == "liability_unlimited")
    assert finding["validation_status"] == "unverified"
    assert "unsupported_explanation" in finding["validation_error_categories"]


@pytest.mark.asyncio
async def test_severity_correction_retry_succeeds(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(db_session, run_id, severity="low")

    validation = await validate_findings(
        async_client, document_id, run_id, max_retries=2
    )
    finding = next(item for item in validation["findings"] if item["rule_id"] == "liability_unlimited")
    assert finding["severity"] == "critical"
    assert finding["validation_status"] == "verified"
    assert validation["run"]["retries_attempted"] == 1
    stages = [attempt["stage"] for attempt in validation["attempts"]]
    assert stages == ["initial", "retry"]


class TimeoutRetryHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def retry(self, finding, feedback, target, db):
        self.calls += 1
        raise ProviderTimeoutError("simulated correction timeout")


@pytest.mark.asyncio
async def test_retry_timeouts_are_bounded_and_never_approve(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    await tamper_finding(
        db_session,
        run_id,
        contract_quote="Fabricated quote that is not in the clause.",
    )

    handler = TimeoutRetryHandler()
    service = EvidenceValidationService(settings=get_settings(), retry_handler=handler)
    run, findings, attempts = await service.validate_findings(
        document_id=document_id,
        db=db_session,
        analysis_run_id=run_id,
        max_retries=2,
    )

    assert handler.calls == 2
    assert run.retries_attempted == 2
    assert run.unverified_count == 1
    finding = findings[0]
    assert finding.validation_status == "unverified"
    assert finding.validation_attempts == 3
    assert any(
        attempt.retry_error_category == "retry_timeout" for attempt in attempts
    )
    assert all(attempt.outcome != "verified" for attempt in attempts)


@pytest.mark.asyncio
async def test_missing_evidence_is_a_distinct_non_approved_outcome(
    async_client: AsyncClient,
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
    await extract_clauses(
        async_client,
        document_id,
        [
            clause_candidate(
                "indemnity",
                "The vendor shall indemnify the Company against all third-party claims.",
                "Vendor indemnity.",
            )
        ],
    )
    await retrieve_policies(async_client, document_id)
    analysis = await analyze_risk(async_client, document_id)
    finding = next(
        item for item in analysis["findings"] if item["finding_type"] == "missing_evidence"
    )
    assert finding["validation_status"] == "missing_evidence"
    assert finding["review_status"] == "needs_review"

    runs = await async_client.get(
        f"/api/v1/documents/{document_id}/validation-runs"
    )
    assert runs.json()["runs"][0]["missing_evidence_count"] == 1
    assert runs.json()["runs"][0]["verified_count"] == 0


@pytest.mark.asyncio
async def test_duplicate_findings_are_flagged_not_verified(
    async_client: AsyncClient, db_session
):
    analysis = await create_liability_analysis(async_client)
    document_id = analysis["document_id"]
    run_id = analysis["run"]["run_id"]
    original = (
        await db_session.execute(
            select(RiskFinding).where(RiskFinding.analysis_run_id == run_id)
        )
    ).scalars().first()
    assert original is not None
    duplicate = RiskFinding(
        id=str(uuid.uuid4()),
        document_id=original.document_id,
        clause_id=original.clause_id,
        clause_category=original.clause_category,
        retrieval_run_id=original.retrieval_run_id,
        analysis_run_id=original.analysis_run_id,
        finding_type=original.finding_type,
        risk_category=original.risk_category,
        severity=original.severity,
        severity_basis=original.severity_basis,
        rule_id=original.rule_id,
        contract_quote=original.contract_quote,
        contract_source_reference=original.contract_source_reference,
        contract_page_number=original.contract_page_number,
        policy_quote=original.policy_quote,
        policy_source_reference=original.policy_source_reference,
        policy_page_number=original.policy_page_number,
        policy_id=original.policy_id,
        policy_version=original.policy_version,
        explanation=original.explanation,
        confidence=original.confidence,
        review_status=original.review_status,
        suggested_question=original.suggested_question,
        analysis_model=original.analysis_model,
        policy_versions=original.policy_versions,
        fingerprint=original.fingerprint,
        validation_status=original.validation_status,
        validation_attempts=original.validation_attempts,
    )
    db_session.add(duplicate)
    await db_session.commit()

    validation = await validate_findings(async_client, document_id, run_id, max_retries=0)
    assert validation["run"]["needs_review_count"] == 1
    duplicate_payload = next(
        item for item in validation["findings"] if item["finding_id"] == duplicate.id
    )
    assert duplicate_payload["validation_status"] == "needs_review"
    assert "duplicate_finding" in duplicate_payload["validation_error_categories"]
