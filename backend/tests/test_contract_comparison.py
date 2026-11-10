import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.risk import get_risk_analysis_service
from app.db.models import (
    Clause,
    ClauseExtractionRun,
    Document,
    DocumentStatus,
    ExtractionRunStatus,
    PolicyRetrievalRun,
    RiskAnalysisRun,
    RiskFinding,
)
from app.main import app

AUTH_HEADERS = {
    "X-Reviewer-ID": "comparison-tester",
    "X-Workflow-Key": "dev-workflow-review-key",
}

LIABILITY = (
    "The vendor's aggregate liability under this Agreement shall be unlimited "
    "for any breach."
)
TERMINATION_OLD = (
    "Company may terminate this Agreement for convenience with ten (10) days' "
    "prior written notice."
)
TERMINATION_NEW = (
    "Company may terminate this Agreement for convenience with thirty (30) days' "
    "prior written notice."
)
PAYMENT = "Customer shall pay all invoices within sixty (60) days of receipt."


async def _create_document(
    db: AsyncSession,
    name: str,
    clauses: list[tuple[str, str, str]],
) -> tuple[Document, list[Clause]]:
    document = Document(
        id=str(uuid.uuid4()),
        original_filename=name,
        stored_path=f"/tmp/{name}",
        file_size_bytes=100,
        mime_type="application/pdf",
        file_hash_sha256=uuid.uuid4().hex * 2,
        status=DocumentStatus.COMPLETED,
        owner_reviewer_id="comparison-tester",
        total_pages=1,
        total_characters=1000,
    )
    run = ClauseExtractionRun(
        id=str(uuid.uuid4()),
        document_id=document.id,
        status=ExtractionRunStatus.COMPLETED,
        provider="mock",
        model_name="mock-clause-extractor",
        total_chunks=1,
        candidates_received=len(clauses),
        clauses_persisted=len(clauses),
    )
    db.add(document)
    db.add(run)
    records: list[Clause] = []
    for index, (category, heading, text) in enumerate(clauses):
        clause = Clause(
            id=str(uuid.uuid4()),
            document_id=document.id,
            extraction_run_id=run.id,
            category=category,
            source_text=text,
            normalized_summary=text,
            page_number=1,
            section_heading=heading,
            start_char_offset=index * 100,
            end_char_offset=index * 100 + len(text),
            confidence=0.95,
            validation_status="valid",
        )
        db.add(clause)
        records.append(clause)
    await db.commit()
    return document, records


async def _add_findings(
    db: AsyncSession,
    document: Document,
    clauses: list[Clause],
    findings: list[tuple[str, str, str, str, str]],
) -> None:
    retrieval = PolicyRetrievalRun(
        id=str(uuid.uuid4()),
        document_id=document.id,
        status=ExtractionRunStatus.COMPLETED,
        embedding_provider="mock",
        embedding_model="mock",
        clauses_processed=len(clauses),
        evidence_count=0,
        missing_coverage_count=0,
        policy_versions=json.dumps(["1.0.0"]),
    )
    analysis = RiskAnalysisRun(
        id=str(uuid.uuid4()),
        document_id=document.id,
        retrieval_run_id=retrieval.id,
        status=ExtractionRunStatus.COMPLETED,
        provider="mock",
        model_name="mock-risk-analyzer",
        clauses_analyzed=len(clauses),
        findings_count=len(findings),
        model_analysis_enabled=True,
        policy_versions=json.dumps(["1.0.0"]),
    )
    db.add(retrieval)
    db.add(analysis)
    clause_by_category = {clause.category: clause for clause in clauses}
    for rule_id, category, finding_type, severity, quote in findings:
        db.add(
            RiskFinding(
                id=str(uuid.uuid4()),
                document_id=document.id,
                clause_id=clause_by_category.get(category).id
                if clause_by_category.get(category)
                else None,
                clause_category=category,
                retrieval_run_id=retrieval.id,
                analysis_run_id=analysis.id,
                finding_type=finding_type,
                risk_category=category,
                severity=severity,
                severity_basis="policy_rule",
                rule_id=rule_id,
                contract_quote=quote,
                contract_source_reference=(
                    f"clause:{clause_by_category[category].id}"
                    if category in clause_by_category
                    else None
                ),
                explanation="Deterministic test finding.",
                review_status="needs_review",
                suggested_question="Review this clause.",
                analysis_model="policy-rule-engine",
                validation_status="verified",
                policy_versions=json.dumps(["1.0.0"]),
            )
        )
    await db.commit()


@pytest.mark.asyncio
async def test_comparison_requires_reviewer_auth(async_client: AsyncClient, db_session):
    base, _ = await _create_document(
        db_session, "base.pdf", [("liability", "1. Liability", LIABILITY)]
    )
    target, _ = await _create_document(
        db_session, "target.pdf", [("liability", "1. Liability", LIABILITY)]
    )
    response = await async_client.post(
        "/api/v1/comparisons",
        json={"base_document_id": base.id, "target_document_id": target.id},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_comparison_classifies_clause_and_finding_changes(
    auth_client: AsyncClient, db_session: AsyncSession
):
    base, base_clauses = await _create_document(
        db_session,
        "base.pdf",
        [
            ("liability", "1. Limitation of Liability", LIABILITY),
            ("termination", "2. Termination", TERMINATION_OLD),
            ("confidentiality", "3. Confidentiality", "Confidential information is protected."),
        ],
    )
    target, target_clauses = await _create_document(
        db_session,
        "target.pdf",
        [
            ("liability", "1. Limitation of Liability", LIABILITY),
            ("termination", "2. Termination", TERMINATION_NEW),
            ("payment", "3. Payment Terms", PAYMENT),
        ],
    )
    await _add_findings(
        db_session,
        base,
        base_clauses,
        [
            ("liability_unlimited", "liability", "policy_deviation", "critical", LIABILITY),
            (
                "termination_notice_shortfall",
                "termination",
                "policy_deviation",
                "high",
                TERMINATION_OLD,
            ),
        ],
    )
    await _add_findings(
        db_session,
        target,
        target_clauses,
        [
            ("liability_unlimited", "liability", "policy_deviation", "critical", LIABILITY),
            (
                "payment_period_exceeds_policy",
                "payment",
                "policy_deviation",
                "medium",
                PAYMENT,
            ),
        ],
    )

    response = await auth_client.post(
        "/api/v1/comparisons",
        headers=AUTH_HEADERS,
        json={"base_document_id": base.id, "target_document_id": target.id},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["clauses_added"] == 1
    assert body["clauses_removed"] == 1
    assert body["clauses_modified"] == 1
    assert body["clauses_unchanged"] == 1
    assert body["findings_new"] == 1
    assert body["findings_resolved"] == 1
    assert body["findings_persisted"] == 1
    assert body["base_analysis_run_id"]
    assert body["target_analysis_run_id"]
    assert body["notice"]

    changed = {item["change_type"] for item in body["clause_changes"]}
    assert {"added", "removed", "modified", "unchanged"}.issubset(changed)
    assert body["affected_clause_ids"]

    listed = await auth_client.get(
        f"/api/v1/comparisons?document_id={target.id}", headers=AUTH_HEADERS
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = await auth_client.get(
        f"/api/v1/comparisons/{body['comparison_id']}", headers=AUTH_HEADERS
    )
    assert detail.status_code == 200
    assert detail.json()["comparison_id"] == body["comparison_id"]


class _RecordingRiskAnalysis:
    def __init__(self) -> None:
        self.calls: list[list[str] | None] = []

    async def analyze(self, document_id, db, clause_ids=None):
        self.calls.append(clause_ids)
        return None, []


@pytest.mark.asyncio
async def test_comparison_reruns_only_affected_target_clauses(
    auth_client: AsyncClient, db_session: AsyncSession
):
    base, _ = await _create_document(
        db_session, "base.pdf", [("termination", "1. Termination", TERMINATION_OLD)]
    )
    target, target_clauses = await _create_document(
        db_session, "target.pdf", [("termination", "1. Termination", TERMINATION_NEW)]
    )
    recorder = _RecordingRiskAnalysis()
    app.dependency_overrides[get_risk_analysis_service] = lambda: recorder
    try:
        response = await auth_client.post(
            "/api/v1/comparisons",
            headers=AUTH_HEADERS,
            json={
                "base_document_id": base.id,
                "target_document_id": target.id,
                "reanalyze_target": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_risk_analysis_service, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reanalysis_requested"] is True
    assert body["reanalysis_performed"] is True
    assert recorder.calls == [[target_clauses[0].id]]
