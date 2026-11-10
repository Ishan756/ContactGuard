import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.authorization import require_document_access
from app.core.config import Settings, get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.factory import get_embedding_provider
from app.core.llm.base import LLMProvider
from app.core.llm.factory import get_llm_provider
from app.core.security import ReviewerPrincipal, require_reviewer
from app.db.models import (
    EvidenceValidationAttempt,
    EvidenceValidationRun,
    ExtractionRunStatus,
    PolicyRetrievalEvidence,
    PolicyRetrievalRun,
    RiskAnalysisRun,
    RiskFinding,
)
from app.db.session import get_db
from app.schemas.risk import (
    ClauseRetrievalResult,
    FindingType,
    PolicyEvidence,
    PolicyRetrievalRequest,
    PolicyRetrievalResponse,
    PolicyRetrievalRunListResponse,
    PolicyRetrievalRunResponse,
    ReviewStatus,
    RiskAnalysisRequest,
    RiskAnalysisResponse,
    RiskAnalysisRunListResponse,
    RiskAnalysisRunResponse,
    RiskFindingListResponse,
    RiskFindingResponse,
    RiskPriority,
    SeverityBasis,
    ValidationAttemptStage,
    ValidationErrorCategory,
    ValidationStatus,
)
from app.schemas.validation import (
    EvidenceValidationAttemptResponse,
    EvidenceValidationRequest,
    EvidenceValidationResponse,
    EvidenceValidationRunListResponse,
    EvidenceValidationRunResponse,
    ValidationFeedbackItem,
)
from app.services.risk.analysis import RiskAnalysisService
from app.services.risk.retrieval import ClauseRetrieval, PolicyRetrievalService
from app.services.risk.validation import EvidenceValidationService
from app.services.vector.qdrant_service import QdrantVectorService

router = APIRouter(prefix="/documents", tags=["Policy Retrieval & Risk Analysis"])


def get_policy_retrieval_service(
    settings: Settings = Depends(get_settings),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> PolicyRetrievalService:
    return PolicyRetrievalService(
        vector_service=QdrantVectorService(settings),
        embedding_provider=embedding_provider,
        settings=settings,
    )


def get_risk_analysis_service(
    settings: Settings = Depends(get_settings),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    retrieval_service: PolicyRetrievalService = Depends(get_policy_retrieval_service),
) -> RiskAnalysisService:
    return RiskAnalysisService(
        llm_provider=llm_provider,
        retrieval_service=retrieval_service,
        settings=settings,
    )


def get_evidence_validation_service(
    settings: Settings = Depends(get_settings),
) -> EvidenceValidationService:
    return EvidenceValidationService(settings=settings)


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _map_evidence(row: PolicyRetrievalEvidence) -> PolicyEvidence:
    return PolicyEvidence(
        chunk_id=row.chunk_id,
        source_identifier=row.source_identifier,
        policy_id=row.policy_id,
        policy_name=row.policy_name,
        policy_version=row.policy_version,
        policy_status=row.policy_status,
        category=row.category,
        section_heading=row.section_heading,
        page_number=row.page_number,
        start_char_offset=row.start_char_offset,
        end_char_offset=row.end_char_offset,
        text=row.text,
        similarity_score=row.similarity_score,
    )


def map_retrieval_run_response(run: PolicyRetrievalRun) -> PolicyRetrievalRunResponse:
    return PolicyRetrievalRunResponse(
        run_id=run.id,
        document_id=run.document_id,
        status=ExtractionRunStatus(run.status),
        embedding_provider=run.embedding_provider,
        embedding_model=run.embedding_model,
        clauses_processed=run.clauses_processed,
        evidence_count=run.evidence_count,
        missing_coverage_count=run.missing_coverage_count,
        policy_statuses=_parse_json_list(run.policy_statuses),
        policy_versions=_parse_json_list(run.policy_versions),
        warnings=_parse_json_list(run.warnings),
        error_message=run.error_message,
        created_at=_format_datetime(run.created_at) or "",
        completed_at=_format_datetime(run.completed_at),
    )


def map_clause_retrieval(result: ClauseRetrieval) -> ClauseRetrievalResult:
    return ClauseRetrievalResult(
        clause_id=result.clause.id,
        category=result.clause.category,
        source_text=result.clause.source_text,
        normalized_summary=result.clause.normalized_summary,
        coverage_status=result.coverage_status,
        coverage_note=result.coverage_note,
        queries=result.queries,
        evidence=[
            PolicyEvidence(
                chunk_id=item.chunk_id,
                source_identifier=item.source_identifier,
                policy_id=item.policy_id,
                policy_name=item.policy_name,
                policy_version=item.policy_version,
                policy_status=item.policy_status,
                category=item.category,
                section_heading=item.section_heading,
                page_number=item.page_number,
                start_char_offset=item.start_char_offset,
                end_char_offset=item.end_char_offset,
                text=item.text,
                similarity_score=item.similarity_score,
            )
            for item in result.evidence
        ],
    )


def map_analysis_run_response(run: RiskAnalysisRun) -> RiskAnalysisRunResponse:
    return RiskAnalysisRunResponse(
        run_id=run.id,
        document_id=run.document_id,
        retrieval_run_id=run.retrieval_run_id,
        status=ExtractionRunStatus(run.status),
        provider=run.provider,
        model_name=run.model_name,
        clauses_analyzed=run.clauses_analyzed,
        findings_count=run.findings_count,
        model_analysis_enabled=run.model_analysis_enabled,
        policy_versions=_parse_json_list(run.policy_versions),
        warnings=_parse_json_list(run.warnings),
        error_message=run.error_message,
        created_at=_format_datetime(run.created_at) or "",
        completed_at=_format_datetime(run.completed_at),
    )


def _validation_categories(value: str | None) -> list[ValidationErrorCategory]:
    categories: list[ValidationErrorCategory] = []
    for item in _parse_json_list(value):
        try:
            categories.append(ValidationErrorCategory(item))
        except ValueError:
            continue
    return categories


def _validation_feedback(value: str | None) -> list[ValidationFeedbackItem]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    feedback: list[ValidationFeedbackItem] = []
    for item in parsed:
        try:
            feedback.append(ValidationFeedbackItem.model_validate(item))
        except Exception:
            continue
    return feedback


def map_finding_response(finding: RiskFinding) -> RiskFindingResponse:
    try:
        validation_status = ValidationStatus(finding.validation_status)
    except ValueError:
        validation_status = ValidationStatus.PENDING
    return RiskFindingResponse(
        finding_id=finding.id,
        document_id=finding.document_id,
        clause_id=finding.clause_id,
        clause_category=finding.clause_category,
        retrieval_run_id=finding.retrieval_run_id,
        analysis_run_id=finding.analysis_run_id,
        finding_type=FindingType(finding.finding_type),
        risk_category=finding.risk_category,
        severity=RiskPriority(finding.severity),
        severity_basis=SeverityBasis(finding.severity_basis),
        rule_id=finding.rule_id,
        contract_quote=finding.contract_quote,
        contract_source_reference=finding.contract_source_reference,
        contract_page_number=finding.contract_page_number,
        policy_quote=finding.policy_quote,
        policy_source_reference=finding.policy_source_reference,
        policy_page_number=finding.policy_page_number,
        policy_id=finding.policy_id,
        policy_version=finding.policy_version,
        explanation=finding.explanation,
        confidence=finding.confidence,
        review_status=ReviewStatus(finding.review_status),
        validation_status=validation_status,
        validation_attempts=finding.validation_attempts or 0,
        validation_error_categories=_validation_categories(
            finding.validation_error_categories
        ),
        last_validated_at=_format_datetime(finding.last_validated_at),
        suggested_question=finding.suggested_question,
        analysis_model=finding.analysis_model,
        policy_versions=_parse_json_list(finding.policy_versions),
        created_at=_format_datetime(finding.created_at) or "",
    )


def map_validation_run_response(
    run: EvidenceValidationRun,
) -> EvidenceValidationRunResponse:
    return EvidenceValidationRunResponse(
        validation_run_id=run.id,
        document_id=run.document_id,
        analysis_run_id=run.analysis_run_id,
        retrieval_run_id=run.retrieval_run_id,
        status=ExtractionRunStatus(run.status),
        max_retries=run.max_retries,
        findings_validated=run.findings_validated,
        verified_count=run.verified_count,
        unverified_count=run.unverified_count,
        needs_review_count=run.needs_review_count,
        missing_evidence_count=run.missing_evidence_count,
        inconclusive_count=run.inconclusive_count,
        retries_attempted=run.retries_attempted,
        warnings=_parse_json_list(run.warnings),
        error_message=run.error_message,
        created_at=_format_datetime(run.created_at) or "",
        completed_at=_format_datetime(run.completed_at),
    )


def map_validation_attempt_response(
    attempt: EvidenceValidationAttempt,
) -> EvidenceValidationAttemptResponse:
    try:
        stage = ValidationAttemptStage(attempt.stage)
    except ValueError:
        stage = ValidationAttemptStage.INITIAL
    try:
        outcome = ValidationStatus(attempt.outcome)
    except ValueError:
        outcome = ValidationStatus.UNVERIFIED
    retry_error_category = None
    if attempt.retry_error_category:
        try:
            retry_error_category = ValidationErrorCategory(
                attempt.retry_error_category
            )
        except ValueError:
            retry_error_category = None
    return EvidenceValidationAttemptResponse(
        attempt_id=attempt.id,
        validation_run_id=attempt.validation_run_id,
        finding_id=attempt.finding_id,
        attempt_number=attempt.attempt_number,
        stage=stage,
        outcome=outcome,
        retry_target=attempt.retry_target,  # pydantic parses the enum value
        error_categories=_validation_categories(attempt.error_categories),
        feedback=_validation_feedback(attempt.feedback),
        retry_error_category=retry_error_category,
        created_at=_format_datetime(attempt.created_at) or "",
        completed_at=_format_datetime(attempt.completed_at),
        duration_ms=attempt.duration_ms,
    )


@router.post(
    "/{document_id}/retrieve-policies",
    response_model=PolicyRetrievalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Retrieve active policy evidence for extracted clauses",
    description=(
        "Embeds deterministic clause queries and retrieves active policy passages from Qdrant. "
        "Draft and archived policies are excluded by default, and clauses with no evidence are "
        "explicitly marked as missing coverage."
    ),
)
async def retrieve_policies(
    document_id: str,
    request: PolicyRetrievalRequest | None = None,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: PolicyRetrievalService = Depends(get_policy_retrieval_service),
) -> PolicyRetrievalResponse:
    await require_document_access(document_id, db, principal)
    run, results = await service.retrieve(
        document_id=document_id, db=db, request=request
    )
    return PolicyRetrievalResponse(
        document_id=document_id,
        run=map_retrieval_run_response(run),
        clauses=[map_clause_retrieval(result) for result in results],
    )


@router.get(
    "/{document_id}/retrieval-runs",
    response_model=PolicyRetrievalRunListResponse,
    summary="List policy retrieval runs for a document",
)
async def list_retrieval_runs(
    document_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: PolicyRetrievalService = Depends(get_policy_retrieval_service),
) -> PolicyRetrievalRunListResponse:
    await require_document_access(document_id, db, principal)
    runs, total = await service.list_runs(
        document_id=document_id, db=db, limit=limit, offset=offset
    )
    return PolicyRetrievalRunListResponse(
        document_id=document_id,
        total=total,
        runs=[map_retrieval_run_response(run) for run in runs],
    )


@router.post(
    "/{document_id}/analyze-risk",
    response_model=RiskAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze clause compliance risks against retrieved policy evidence",
    description=(
        "Runs deterministic policy rules first (liability caps, termination notice, payment "
        "periods) and missing-clause checks. Model analysis is only used when no deterministic "
        "rule fires, policy evidence exists, and the model is enabled. Severity comes from "
        "policy rules/configuration, never model confidence."
    ),
)
async def analyze_risk(
    document_id: str,
    request: RiskAnalysisRequest | None = None,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
    validation_service: EvidenceValidationService = Depends(get_evidence_validation_service),
) -> RiskAnalysisResponse:
    await require_document_access(document_id, db, principal)
    request = request or RiskAnalysisRequest()
    run, findings = await service.analyze(
        document_id=document_id,
        db=db,
        retrieval_run_id=request.retrieval_run_id,
        enable_model_analysis=request.enable_model_analysis,
    )
    should_validate = (
        validation_service.settings.validation_enable
        if request.enable_validation is None
        else request.enable_validation
    )
    if should_validate and findings:
        _, findings, _ = await validation_service.validate_findings(
            document_id=document_id,
            db=db,
            analysis_run_id=run.id,
            max_retries=request.validation_max_retries,
        )
    return RiskAnalysisResponse(
        document_id=document_id,
        run=map_analysis_run_response(run),
        findings=[map_finding_response(finding) for finding in findings],
    )


@router.get(
    "/{document_id}/findings",
    response_model=RiskFindingListResponse,
    summary="List risk findings for the latest analysis run",
)
async def list_findings(
    document_id: str,
    analysis_run_id: str | None = Query(
        default=None, description="Filter to a specific analysis run (defaults to latest)"
    ),
    severity: str | None = Query(default=None, description="Filter by review priority"),
    category: str | None = Query(default=None, description="Filter by risk category"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
) -> RiskFindingListResponse:
    await require_document_access(document_id, db, principal)
    findings, total = await service.list_findings(
        document_id=document_id,
        db=db,
        analysis_run_id=analysis_run_id,
        severity=severity,
        category=category,
        limit=limit,
        offset=offset,
    )
    return RiskFindingListResponse(
        document_id=document_id,
        total=total,
        findings=[map_finding_response(finding) for finding in findings],
    )


@router.get(
    "/{document_id}/findings/{finding_id}",
    response_model=RiskFindingResponse,
    summary="Get a single risk finding with contract and policy citations",
)
async def get_finding(
    document_id: str,
    finding_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
) -> RiskFindingResponse:
    await require_document_access(document_id, db, principal)
    finding = await service.get_finding(
        document_id=document_id, finding_id=finding_id, db=db
    )
    return map_finding_response(finding)


@router.get(
    "/{document_id}/analysis-runs",
    response_model=RiskAnalysisRunListResponse,
    summary="List risk analysis runs for a document",
)
async def list_analysis_runs(
    document_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: RiskAnalysisService = Depends(get_risk_analysis_service),
) -> RiskAnalysisRunListResponse:
    await require_document_access(document_id, db, principal)
    runs, total = await service.list_runs(
        document_id=document_id, db=db, limit=limit, offset=offset
    )
    return RiskAnalysisRunListResponse(
        document_id=document_id,
        total=total,
        runs=[map_analysis_run_response(run) for run in runs],
    )


@router.post(
    "/{document_id}/validate-findings",
    response_model=EvidenceValidationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Independently validate risk findings and request bounded corrections",
    description=(
        "Re-checks each finding against persisted contract clauses, policy chunks, retrieval "
        "evidence, page numbers, severity configuration, and explanation support. Failed "
        "findings may be corrected by a bounded, deterministic retry loop; exhausted findings "
        "remain unverified and are never silently approved."
    ),
)
async def validate_findings(
    document_id: str,
    request: EvidenceValidationRequest | None = None,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: EvidenceValidationService = Depends(get_evidence_validation_service),
) -> EvidenceValidationResponse:
    await require_document_access(document_id, db, principal)
    request = request or EvidenceValidationRequest()
    run, findings, attempts = await service.validate(
        document_id=document_id, request=request, db=db
    )
    return EvidenceValidationResponse(
        document_id=document_id,
        run=map_validation_run_response(run),
        findings=[map_finding_response(finding) for finding in findings],
        attempts=[map_validation_attempt_response(attempt) for attempt in attempts],
    )


@router.get(
    "/{document_id}/validation-runs",
    response_model=EvidenceValidationRunListResponse,
    summary="List evidence validation runs",
)
async def list_validation_runs(
    document_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: EvidenceValidationService = Depends(get_evidence_validation_service),
) -> EvidenceValidationRunListResponse:
    await require_document_access(document_id, db, principal)
    runs, total = await service.list_runs(
        document_id=document_id, db=db, limit=limit, offset=offset
    )
    return EvidenceValidationRunListResponse(
        document_id=document_id,
        total=total,
        runs=[map_validation_run_response(run) for run in runs],
    )


@router.get(
    "/{document_id}/validation-runs/{validation_run_id}",
    response_model=EvidenceValidationResponse,
    summary="Get a validation run, its findings, and every attempt",
)
async def get_validation_run(
    document_id: str,
    validation_run_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: EvidenceValidationService = Depends(get_evidence_validation_service),
) -> EvidenceValidationResponse:
    await require_document_access(document_id, db, principal)
    run = await service.get_run(
        document_id=document_id, validation_run_id=validation_run_id, db=db
    )
    findings = await service.get_run_findings(run, db)
    attempts = await service.get_attempts(validation_run_id=run.id, db=db)
    return EvidenceValidationResponse(
        document_id=document_id,
        run=map_validation_run_response(run),
        findings=[map_finding_response(finding) for finding in findings],
        attempts=[map_validation_attempt_response(attempt) for attempt in attempts],
    )
