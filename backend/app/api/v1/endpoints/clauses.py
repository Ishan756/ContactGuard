import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.authorization import require_document_access
from app.core.config import Settings, get_settings
from app.core.llm.base import LLMProvider
from app.core.llm.factory import get_llm_provider
from app.core.security import ReviewerPrincipal, require_reviewer
from app.db.models import (
    Clause,
    ClauseExtractionRun,
    ClauseValidationStatus,
    ExtractionRunStatus,
)
from app.db.session import get_db
from app.schemas.clause import (
    ClauseExtractionResponse,
    ClauseListResponse,
    ClauseResponse,
    ExtractionRunListResponse,
    ExtractionRunResponse,
)
from app.services.clause.service import ClauseExtractionService

router = APIRouter(prefix="/documents", tags=["Clause Extraction"])


def get_clause_extraction_service(
    settings: Settings = Depends(get_settings),
    llm_provider: LLMProvider = Depends(get_llm_provider),
) -> ClauseExtractionService:
    return ClauseExtractionService(llm_provider=llm_provider, settings=settings)


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


def map_clause_response(clause: Clause) -> ClauseResponse:
    return ClauseResponse(
        clause_id=clause.id,
        document_id=clause.document_id,
        extraction_run_id=clause.extraction_run_id,
        category=clause.category,
        source_text=clause.source_text,
        normalized_summary=clause.normalized_summary,
        page_number=clause.page_number,
        section_heading=clause.section_heading,
        start_char_offset=clause.start_char_offset,
        end_char_offset=clause.end_char_offset,
        confidence=clause.confidence,
        validation_status=ClauseValidationStatus(clause.validation_status),
        validation_notes=clause.validation_notes,
        source_chunk_ids=_parse_json_list(clause.source_chunk_ids),
        created_at=_format_datetime(clause.created_at) or "",
    )


def map_run_response(run: ClauseExtractionRun) -> ExtractionRunResponse:
    return ExtractionRunResponse(
        run_id=run.id,
        document_id=run.document_id,
        status=ExtractionRunStatus(run.status),
        provider=run.provider,
        model_name=run.model_name,
        total_chunks=run.total_chunks,
        candidates_received=run.candidates_received,
        clauses_persisted=run.clauses_persisted,
        duplicates_merged=run.duplicates_merged,
        candidates_rejected=run.candidates_rejected,
        warnings=_parse_json_list(run.warnings),
        error_message=run.error_message,
        created_at=_format_datetime(run.created_at) or "",
        completed_at=_format_datetime(run.completed_at),
    )


@router.post(
    "/{document_id}/extract-clauses",
    response_model=ClauseExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Extract validated clauses from an ingested contract",
    description=(
        "Runs the Clause Extraction Agent over bounded, overlapping document chunks. "
        "Clauses are validated against exact source citations, deduplicated deterministically, "
        "and persisted with the document and extraction run. No legal risk scores are assigned."
    ),
)
async def extract_clauses(
    document_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ClauseExtractionService = Depends(get_clause_extraction_service),
) -> ClauseExtractionResponse:
    await require_document_access(document_id, db, principal)
    run, clauses = await service.extract_clauses(document_id=document_id, db=db)
    return ClauseExtractionResponse(
        document_id=document_id,
        run=map_run_response(run),
        clauses=[map_clause_response(clause) for clause in clauses],
    )


@router.get(
    "/{document_id}/clauses",
    response_model=ClauseListResponse,
    summary="List extracted clauses for a document",
)
async def list_clauses(
    document_id: str,
    category: str | None = Query(default=None, description="Filter by canonical clause category"),
    extraction_run_id: str | None = Query(
        default=None, description="Filter to a specific extraction run"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ClauseExtractionService = Depends(get_clause_extraction_service),
) -> ClauseListResponse:
    await require_document_access(document_id, db, principal)
    clauses, total = await service.list_clauses(
        document_id=document_id,
        db=db,
        category=category,
        extraction_run_id=extraction_run_id,
        limit=limit,
        offset=offset,
    )
    return ClauseListResponse(
        document_id=document_id,
        total=total,
        clauses=[map_clause_response(clause) for clause in clauses],
    )


@router.get(
    "/{document_id}/clauses/{clause_id}",
    response_model=ClauseResponse,
    summary="Get a single extracted clause with source citation",
)
async def get_clause(
    document_id: str,
    clause_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ClauseExtractionService = Depends(get_clause_extraction_service),
) -> ClauseResponse:
    await require_document_access(document_id, db, principal)
    clause = await service.get_clause(document_id=document_id, clause_id=clause_id, db=db)
    return map_clause_response(clause)


@router.get(
    "/{document_id}/extraction-runs",
    response_model=ExtractionRunListResponse,
    summary="List clause extraction runs for a document",
)
async def list_extraction_runs(
    document_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db),
    service: ClauseExtractionService = Depends(get_clause_extraction_service),
) -> ExtractionRunListResponse:
    await require_document_access(document_id, db, principal)
    runs, total = await service.list_runs(
        document_id=document_id, db=db, limit=limit, offset=offset
    )
    return ExtractionRunListResponse(
        document_id=document_id,
        total=total,
        runs=[map_run_response(run) for run in runs],
    )
