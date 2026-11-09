import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, status
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.endpoints.risk import map_finding_response
from app.core.config import Settings, get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.factory import get_embedding_provider
from app.core.llm.base import LLMProvider
from app.core.llm.factory import get_llm_provider
from app.core.security import ReviewerPrincipal, require_reviewer
from app.db.models import ReviewDecisionType, WorkflowEvent, WorkflowRun, WorkflowStatus
from app.db.session import get_session_factory
from app.schemas.workflow import (
    ReviewDecisionResponse,
    WorkflowEventResponse,
    WorkflowResultsResponse,
    WorkflowResumeRequest,
    WorkflowRunListResponse,
    WorkflowRunResponse,
    WorkflowStartRequest,
)
from app.services.clause.service import ClauseExtractionService
from app.services.risk.analysis import RiskAnalysisService
from app.services.risk.retrieval import PolicyRetrievalService
from app.services.risk.validation import EvidenceValidationService
from app.services.vector.qdrant_service import QdrantVectorService
from app.services.workflow.nodes import WorkflowDependencies
from app.services.workflow.service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["LangGraph Workflow & Human Review"])

_fallback_checkpointer: InMemorySaver | None = None


def get_workflow_checkpointer(request: Request) -> Any:
    checkpointer = getattr(request.app.state, "workflow_checkpointer", None)
    if checkpointer is not None:
        return checkpointer
    global _fallback_checkpointer
    if _fallback_checkpointer is None:
        _fallback_checkpointer = InMemorySaver()
    return _fallback_checkpointer


def get_workflow_service(
    request: Request,
    settings: Settings = Depends(get_settings),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> WorkflowService:
    retrieval = PolicyRetrievalService(
        vector_service=QdrantVectorService(settings),
        embedding_provider=embedding_provider,
        settings=settings,
    )
    deps = WorkflowDependencies(
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
        session_factory=session_factory,
    )
    return WorkflowService(
        dependencies=deps,
        checkpointer=get_workflow_checkpointer(request),
        settings=settings,
    )


def _parse_json_object(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _map_event(event: WorkflowEvent) -> WorkflowEventResponse:
    return WorkflowEventResponse(
        event_id=event.id,
        event_type=event.event_type,
        node=event.node,
        actor_id=event.actor_id,
        status_from=event.status_from,
        status_to=event.status_to,
        message=event.message,
        payload=_parse_json_object(event.payload),
        created_at=_format_datetime(event.created_at) or "",
    )


def map_workflow_response(run: WorkflowRun) -> WorkflowRunResponse:
    decisions = [
        ReviewDecisionResponse(
            decision_id=item.id,
            reviewer_id=item.reviewer_id,
            decision=ReviewDecisionType(item.decision),
            finding_ids=_parse_json_list(item.finding_ids),
            notes=item.notes,
            revision_instructions=item.revision_instructions,
            revision_target=item.revision_target,
            idempotency_key=item.idempotency_key,
            created_at=_format_datetime(item.created_at) or "",
        )
        for item in run.decisions
    ]
    return WorkflowRunResponse(
        workflow_id=run.id,
        thread_id=run.thread_id,
        document_id=run.document_id,
        owner_reviewer_id=run.owner_reviewer_id,
        status=WorkflowStatus(run.status),
        current_node=run.current_node,
        interrupted_node=run.interrupted_node,
        step_count=run.step_count,
        retry_count=run.retry_count,
        revision_count=run.revision_count,
        max_retries=run.max_retries,
        max_steps=run.max_steps,
        clause_extraction_run_id=run.clause_extraction_run_id,
        policy_retrieval_run_id=run.policy_retrieval_run_id,
        risk_analysis_run_id=run.risk_analysis_run_id,
        validation_run_id=run.validation_run_id,
        review_request=_parse_json_object(run.review_request),
        review_report=_parse_json_object(run.review_report),
        state_snapshot=_parse_json_object(run.state_snapshot),
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=_format_datetime(run.created_at) or "",
        updated_at=_format_datetime(run.updated_at) or "",
        started_at=_format_datetime(run.started_at),
        review_requested_at=_format_datetime(run.review_requested_at),
        completed_at=_format_datetime(run.completed_at),
        events=[_map_event(event) for event in run.events],
        decisions=decisions,
    )


@router.post(
    "",
    response_model=WorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a LangGraph contract review workflow",
    description=(
        "Runs clause extraction, policy retrieval, risk analysis, automatic evidence "
        "validation, conditional retries, and pauses for human review when findings exist. "
        "No legal or contractual action is executed."
    ),
)
async def start_workflow(
    request: WorkflowStartRequest,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    service: WorkflowService = Depends(get_workflow_service),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkflowRunResponse:
    run = await service.start_workflow(
        request, principal, idempotency_key=idempotency_key
    )
    return map_workflow_response(run)


@router.get(
    "",
    response_model=WorkflowRunListResponse,
    summary="List workflow runs owned by the authenticated reviewer",
)
async def list_workflows(
    document_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: ReviewerPrincipal = Depends(require_reviewer),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRunListResponse:
    runs, total = await service.list_workflows(
        principal,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return WorkflowRunListResponse(
        runs=[map_workflow_response(run) for run in runs],
        total=total,
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowRunResponse,
    summary="Inspect workflow status, interrupts, events, and decisions",
)
async def get_workflow(
    workflow_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowRunResponse:
    run = await service.get_workflow(workflow_id, principal)
    return map_workflow_response(run)


@router.get(
    "/{workflow_id}/results",
    response_model=WorkflowResultsResponse,
    summary="Retrieve the review report and persisted findings",
)
async def get_workflow_results(
    workflow_id: str,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowResultsResponse:
    run, findings, report = await service.get_results(workflow_id, principal)
    snapshot = _parse_json_object(run.state_snapshot) or {}
    validation = snapshot.get("validation")
    return WorkflowResultsResponse(
        workflow=map_workflow_response(run),
        report=report,
        findings=[map_finding_response(finding) for finding in findings],
        validation_summary=validation if isinstance(validation, dict) else None,
        automatic_verification_complete=bool(run.validation_run_id),
        human_review_complete=bool(
            run.status == WorkflowStatus.COMPLETED.value and run.decisions
        ),
        legal_action_performed=False,
    )


@router.post(
    "/{workflow_id}/resume",
    response_model=WorkflowRunResponse,
    summary="Resume an interrupted human-review workflow",
    description=(
        "Approve, dismiss, or request revision of findings. Resume commands are "
        "authenticated, owner-authorized, appended to an immutable audit trail, and "
        "idempotent when supplied with an Idempotency-Key."
    ),
)
async def resume_workflow(
    workflow_id: str,
    request: WorkflowResumeRequest,
    principal: ReviewerPrincipal = Depends(require_reviewer),
    service: WorkflowService = Depends(get_workflow_service),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> WorkflowRunResponse:
    run = await service.resume_workflow(
        workflow_id,
        request,
        principal,
        idempotency_key=idempotency_key,
    )
    return map_workflow_response(run)
