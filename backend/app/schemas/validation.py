from pydantic import BaseModel, Field

from app.db.models import ExtractionRunStatus
from app.schemas.risk import (
    RetryTarget,
    RiskFindingResponse,
    ValidationAttemptStage,
    ValidationErrorCategory,
    ValidationStatus,
)


class ValidationFeedbackItem(BaseModel):
    category: ValidationErrorCategory = Field(..., description="Specific validation failure")
    field: str = Field(..., description="Finding field implicated by the failure")
    message: str = Field(..., description="Review-safe explanation of the failure")
    retry_target: RetryTarget = Field(
        default=RetryTarget.NONE, description="Step that can correct this failure"
    )


class EvidenceValidationRequest(BaseModel):
    analysis_run_id: str | None = Field(
        default=None, description="Risk analysis run to validate; defaults to the latest run"
    )
    finding_ids: list[str] | None = Field(
        default=None, description="Optional subset of findings to validate"
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Override the configured bounded correction retry limit",
    )
    enable_retries: bool = Field(
        default=True, description="Allow deterministic bounded correction retries"
    )


class EvidenceValidationAttemptResponse(BaseModel):
    attempt_id: str = Field(..., description="Validation attempt identifier")
    validation_run_id: str = Field(..., description="Parent validation run identifier")
    finding_id: str = Field(..., description="Finding that was validated")
    attempt_number: int = Field(..., description="One-based validation attempt number")
    stage: ValidationAttemptStage = Field(..., description="Initial check or correction retry")
    outcome: ValidationStatus = Field(..., description="Outcome of this attempt")
    retry_target: RetryTarget = Field(
        default=RetryTarget.NONE, description="Correction step requested after this attempt"
    )
    error_categories: list[ValidationErrorCategory] = Field(
        default_factory=list, description="Validation failures for this attempt"
    )
    feedback: list[ValidationFeedbackItem] = Field(
        default_factory=list, description="Actionable correction feedback"
    )
    retry_error_category: ValidationErrorCategory | None = Field(
        default=None, description="Failure raised by the correction step, if any"
    )
    created_at: str = Field(..., description="ISO 8601 attempt start timestamp")
    completed_at: str | None = Field(default=None, description="ISO 8601 attempt completion")
    duration_ms: int | None = Field(default=None, description="Attempt duration in milliseconds")


class EvidenceValidationRunResponse(BaseModel):
    validation_run_id: str = Field(..., description="Validation run identifier")
    document_id: str = Field(..., description="Source document identifier")
    analysis_run_id: str = Field(..., description="Risk analysis run validated")
    retrieval_run_id: str = Field(..., description="Policy retrieval run used as evidence source")
    status: ExtractionRunStatus = Field(..., description="Validation run lifecycle status")
    max_retries: int = Field(..., description="Maximum retries allowed per finding")
    findings_validated: int = Field(..., description="Findings checked in this run")
    verified_count: int = Field(..., description="Findings with independently verified evidence")
    unverified_count: int = Field(..., description="Findings that failed validation")
    needs_review_count: int = Field(
        ..., description="Findings requiring human review before use"
    )
    missing_evidence_count: int = Field(
        ..., description="Findings confirmed as retrieval/evidence gaps"
    )
    inconclusive_count: int = Field(
        ..., description="Findings whose evidence could not be conclusively validated"
    )
    retries_attempted: int = Field(..., description="Correction retries attempted")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal validation warnings")
    error_message: str | None = Field(default=None, description="Fatal validation error, if any")
    created_at: str = Field(..., description="ISO 8601 run start timestamp")
    completed_at: str | None = Field(default=None, description="ISO 8601 run completion timestamp")


class EvidenceValidationResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    run: EvidenceValidationRunResponse = Field(..., description="Validation run metadata")
    findings: list[RiskFindingResponse] = Field(
        ..., description="Findings with updated validation state"
    )
    attempts: list[EvidenceValidationAttemptResponse] = Field(
        default_factory=list, description="Every validation and correction attempt"
    )


class EvidenceValidationRunListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total validation runs")
    runs: list[EvidenceValidationRunResponse] = Field(..., description="Runs, newest first")
