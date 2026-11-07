from typing import Any

from pydantic import BaseModel, Field

from app.db.models import ReviewDecisionType, WorkflowStatus
from app.schemas.risk import RetryTarget, RiskFindingResponse


class WorkflowStartRequest(BaseModel):
    document_id: str = Field(..., description="Ingested contract document identifier")
    enable_model_analysis: bool | None = Field(
        default=None,
        description="Override the configured model-assisted risk analysis setting",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Optional workflow-level retry limit override",
    )
    max_steps: int | None = Field(
        default=None,
        ge=5,
        le=100,
        description="Optional maximum graph-step override",
    )


class WorkflowResumeRequest(BaseModel):
    decision: ReviewDecisionType = Field(
        ...,
        description="Human decision: approve, dismiss, or request_revision",
    )
    finding_ids: list[str] | None = Field(
        default=None,
        description="Findings the decision applies to; defaults to all current findings",
    )
    notes: str | None = Field(
        default=None,
        max_length=5000,
        description="Reviewer notes retained in the append-only audit trail",
    )
    revision_instructions: str | None = Field(
        default=None,
        max_length=5000,
        description="Required when decision is request_revision",
    )
    revision_target: RetryTarget = Field(
        default=RetryTarget.ANALYSIS,
        description="Revision target: analysis or retrieval",
    )
    command_id: str | None = Field(
        default=None,
        max_length=160,
        description="Optional idempotency key for this resume command",
    )


class WorkflowEventResponse(BaseModel):
    event_id: str
    event_type: str
    node: str | None = None
    actor_id: str | None = None
    status_from: str | None = None
    status_to: str | None = None
    message: str | None = None
    payload: dict[str, Any] | None = None
    created_at: str


class ReviewDecisionResponse(BaseModel):
    decision_id: str
    reviewer_id: str
    decision: ReviewDecisionType
    finding_ids: list[str] = Field(default_factory=list)
    notes: str | None = None
    revision_instructions: str | None = None
    revision_target: str | None = None
    idempotency_key: str | None = None
    created_at: str


class WorkflowRunResponse(BaseModel):
    workflow_id: str
    thread_id: str
    document_id: str
    owner_reviewer_id: str
    status: WorkflowStatus
    current_node: str | None = None
    interrupted_node: str | None = None
    step_count: int = 0
    retry_count: int = 0
    revision_count: int = 0
    max_retries: int = 0
    max_steps: int = 0
    clause_extraction_run_id: str | None = None
    policy_retrieval_run_id: str | None = None
    risk_analysis_run_id: str | None = None
    validation_run_id: str | None = None
    review_request: dict[str, Any] | None = None
    review_report: dict[str, Any] | None = None
    state_snapshot: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    review_requested_at: str | None = None
    completed_at: str | None = None
    events: list[WorkflowEventResponse] = Field(default_factory=list)
    decisions: list[ReviewDecisionResponse] = Field(default_factory=list)


class WorkflowResultsResponse(BaseModel):
    workflow: WorkflowRunResponse
    report: dict[str, Any] | None = None
    findings: list[RiskFindingResponse] = Field(default_factory=list)
    validation_summary: dict[str, Any] | None = None
    automatic_verification_complete: bool = False
    human_review_complete: bool = False
    legal_action_performed: bool = False
