import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.risk import get_risk_analysis_service
from app.core.config import Settings, get_settings
from app.core.security import ReviewerPrincipal, require_reviewer
from app.db.models import ClauseChange, ContractComparison, FindingChange
from app.db.session import get_db
from app.schemas.comparison import (
    ClauseChangeResponse,
    ContractComparisonListResponse,
    ContractComparisonRequest,
    ContractComparisonResponse,
    FindingChangeResponse,
)
from app.services.comparison.service import ContractComparisonService
from app.services.risk.analysis import RiskAnalysisService

router = APIRouter(prefix="/comparisons", tags=["Contract Version Comparison"])


def get_comparison_service(
    settings: Settings = Depends(get_settings),
    risk_analysis: RiskAnalysisService = Depends(get_risk_analysis_service),
) -> ContractComparisonService:
    return ContractComparisonService(settings=settings, risk_analysis=risk_analysis)


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def map_clause_change(change: ClauseChange) -> ClauseChangeResponse:
    return ClauseChangeResponse(
        change_id=change.id,
        change_type=change.change_type,
        category=change.category,
        base_clause_id=change.base_clause_id,
        target_clause_id=change.target_clause_id,
        base_category=change.base_category,
        target_category=change.target_category,
        base_source_text=change.base_source_text,
        target_source_text=change.target_source_text,
        base_source_reference=change.base_source_reference,
        target_source_reference=change.target_source_reference,
        similarity=change.similarity,
        change_summary=change.change_summary,
        created_at=_format_datetime(change.created_at) or "",
    )


def map_finding_change(change: FindingChange) -> FindingChangeResponse:
    return FindingChangeResponse(
        change_id=change.id,
        change_type=change.change_type,
        finding_type=change.finding_type,
        risk_category=change.risk_category,
        rule_id=change.rule_id,
        base_finding_id=change.base_finding_id,
        target_finding_id=change.target_finding_id,
        base_severity=change.base_severity,
        target_severity=change.target_severity,
        base_validation_status=change.base_validation_status,
        target_validation_status=change.target_validation_status,
        contract_source_reference=change.contract_source_reference,
        explanation=change.explanation,
        created_at=_format_datetime(change.created_at) or "",
    )


def map_comparison(comparison: ContractComparison) -> ContractComparisonResponse:
    return ContractComparisonResponse(
        comparison_id=comparison.id,
        base_document_id=comparison.base_document_id,
        target_document_id=comparison.target_document_id,
        created_by=comparison.created_by,
        status=comparison.status,
        base_analysis_run_id=comparison.base_analysis_run_id,
        target_analysis_run_id=comparison.target_analysis_run_id,
        clauses_added=comparison.clauses_added,
        clauses_removed=comparison.clauses_removed,
        clauses_modified=comparison.clauses_modified,
        clauses_unchanged=comparison.clauses_unchanged,
        clauses_reclassified=comparison.clauses_reclassified,
        findings_new=comparison.findings_new,
        findings_resolved=comparison.findings_resolved,
        findings_persisted=comparison.findings_persisted,
        findings_severity_changed=comparison.findings_severity_changed,
        affected_clause_ids=_parse_json_list(comparison.affected_clause_ids),
        reanalysis_requested=comparison.reanalysis_requested,
        reanalysis_performed=comparison.reanalysis_performed,
        warnings=_parse_json_list(comparison.warnings),
        error_message=comparison.error_message,
        created_at=_format_datetime(comparison.created_at) or "",
        completed_at=_format_datetime(comparison.completed_at),
        clause_changes=[map_clause_change(item) for item in comparison.clause_changes],
        finding_changes=[map_finding_change(item) for item in comparison.finding_changes],
    )


@router.post(
    "",
    response_model=ContractComparisonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compare two contract versions and their latest findings",
    description=(
        "Deterministically matches extracted clauses across two document versions, classifies "
        "added, removed, modified, reclassified, and unchanged clauses, and compares the latest "
        "risk findings. Optionally re-runs analysis on affected clauses in the newer version."
    ),
)
async def create_comparison(
    request: ContractComparisonRequest,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ContractComparisonService = Depends(get_comparison_service),
) -> ContractComparisonResponse:
    comparison = await service.compare(request, principal, db)
    return map_comparison(comparison)


@router.get(
    "",
    response_model=ContractComparisonListResponse,
    summary="List contract version comparisons",
)
async def list_comparisons(
    document_id: str | None = Query(
        default=None, description="Filter comparisons involving this document"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ContractComparisonService = Depends(get_comparison_service),
) -> ContractComparisonListResponse:
    comparisons, total = await service.list(
        db,
        principal,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return ContractComparisonListResponse(
        comparisons=[map_comparison(item) for item in comparisons],
        total=total,
    )


@router.get(
    "/{comparison_id}",
    response_model=ContractComparisonResponse,
    summary="Get a contract version comparison with clause and finding changes",
)
async def get_comparison(
    comparison_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ContractComparisonService = Depends(get_comparison_service),
) -> ContractComparisonResponse:
    comparison = await service.get(comparison_id, db, principal)
    return map_comparison(comparison)
