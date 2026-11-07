from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ExtractionRunStatus


class RiskPriority(StrEnum):
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingType(StrEnum):
    POLICY_DEVIATION = "policy_deviation"
    POSSIBLE_LEGAL_CONCERN = "possible_legal_concern"
    MISSING_CLAUSE = "missing_clause"
    MISSING_EVIDENCE = "missing_evidence"


class ReviewStatus(StrEnum):
    NEEDS_REVIEW = "needs_review"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    NEEDS_REVIEW = "needs_review"
    MISSING_EVIDENCE = "missing_evidence"
    INCONCLUSIVE = "inconclusive"


class ValidationErrorCategory(StrEnum):
    MISSING_CONTRACT_QUOTE = "missing_contract_quote"
    CONTRACT_QUOTE_NOT_FOUND = "contract_quote_not_found"
    CONTRACT_SOURCE_MISSING = "contract_source_missing"
    MISSING_POLICY_QUOTE = "missing_policy_quote"
    POLICY_QUOTE_NOT_FOUND = "policy_quote_not_found"
    POLICY_SOURCE_MISMATCH = "policy_source_mismatch"
    POLICY_SOURCE_NOT_IN_RETRIEVAL = "policy_source_not_in_retrieval"
    DOCUMENT_ID_MISMATCH = "document_id_mismatch"
    CLAUSE_ID_MISMATCH = "clause_id_mismatch"
    RETRIEVAL_RUN_MISMATCH = "retrieval_run_mismatch"
    RETRIEVAL_EVIDENCE_MISSING = "retrieval_evidence_missing"
    POLICY_ID_MISMATCH = "policy_id_mismatch"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"
    PAGE_NUMBER_MISMATCH = "page_number_mismatch"
    UNSUPPORTED_EXPLANATION = "unsupported_explanation"
    SEVERITY_MISMATCH = "severity_mismatch"
    MALFORMED_CITATION = "malformed_citation"
    FINDING_CONTRADICTED_BY_DOCUMENT = "finding_contradicted_by_document"
    EVIDENCE_PRESENT = "evidence_present"
    MISSING_EVIDENCE = "missing_evidence"
    INCONCLUSIVE = "inconclusive"
    DUPLICATE_FINDING = "duplicate_finding"
    RETRY_TIMEOUT = "retry_timeout"
    RETRY_FAILED = "retry_failed"
    UNEXPECTED_FINDING_TYPE = "unexpected_finding_type"


class RetryTarget(StrEnum):
    NONE = "none"
    ANALYSIS = "analysis"
    RETRIEVAL = "retrieval"


class ValidationAttemptStage(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"


class PolicyCoverageStatus(StrEnum):
    COVERED = "covered"
    MISSING = "missing"


class SeverityBasis(StrEnum):
    POLICY_RULE = "policy_rule"
    CONFIGURED_REQUIREMENT = "configured_requirement"
    MODEL_ANALYSIS = "model_analysis"
    RETRIEVAL_GAP = "retrieval_gap"


class PolicyRetrievalRequest(BaseModel):
    policy_versions: list[str] | None = Field(
        default=None,
        description="Optional policy versions to include; defaults to all eligible versions",
    )
    policy_statuses: list[str] | None = Field(
        default=None,
        description="Optional policy statuses to include; defaults to configured statuses",
    )


class PolicyEvidence(BaseModel):
    chunk_id: str = Field(..., description="Policy chunk identifier")
    source_identifier: str = Field(..., description="Stable policy citation locator")
    policy_id: str = Field(..., description="Parent policy identifier")
    policy_name: str = Field(..., description="Parent policy name")
    policy_version: str = Field(..., description="Parent policy version")
    policy_status: str = Field(..., description="Policy lifecycle status at retrieval time")
    category: str | None = Field(default=None, description="Policy domain category")
    section_heading: str | None = Field(default=None, description="Policy section heading")
    page_number: int = Field(..., description="Source page number")
    start_char_offset: int = Field(..., description="Start character offset within the policy")
    end_char_offset: int = Field(..., description="End character offset within the policy")
    text: str = Field(..., description="Retrieved policy passage")
    similarity_score: float = Field(
        ..., description="Semantic similarity only; not evidence of legal compliance"
    )


class ClauseRetrievalResult(BaseModel):
    clause_id: str = Field(..., description="Extracted clause identifier")
    category: str = Field(..., description="Canonical clause category")
    source_text: str = Field(..., description="Verbatim contract clause text")
    normalized_summary: str = Field(..., description="Normalized clause summary")
    coverage_status: PolicyCoverageStatus = Field(
        ..., description="Whether active policy evidence was retrieved for this clause"
    )
    coverage_note: str = Field(..., description="Explicit note when evidence is missing")
    queries: list[str] = Field(..., description="Deterministic retrieval queries used")
    evidence: list[PolicyEvidence] = Field(
        default_factory=list, description="Ranked policy evidence passages"
    )


class PolicyRetrievalRunResponse(BaseModel):
    run_id: str = Field(..., description="Retrieval run identifier")
    document_id: str = Field(..., description="Source document identifier")
    status: ExtractionRunStatus = Field(..., description="Run lifecycle status")
    embedding_provider: str = Field(..., description="Embedding provider name")
    embedding_model: str = Field(..., description="Embedding model name")
    clauses_processed: int = Field(..., description="Clauses searched against policy index")
    evidence_count: int = Field(..., description="Policy evidence passages persisted")
    missing_coverage_count: int = Field(..., description="Clauses with no policy evidence")
    policy_statuses: list[str] = Field(..., description="Policy statuses eligible for retrieval")
    policy_versions: list[str] = Field(..., description="Policy versions eligible for retrieval")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal retrieval warnings")
    error_message: str | None = Field(default=None, description="Fatal run error, if any")
    created_at: str = Field(..., description="ISO 8601 run start timestamp")
    completed_at: str | None = Field(default=None, description="ISO 8601 run completion timestamp")


class PolicyRetrievalResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    run: PolicyRetrievalRunResponse = Field(..., description="Retrieval run metadata")
    clauses: list[ClauseRetrievalResult] = Field(
        ..., description="Per-clause retrieval results with explicit missing coverage"
    )


class PolicyRetrievalRunListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total retrieval runs")
    runs: list[PolicyRetrievalRunResponse] = Field(..., description="Retrieval runs, newest first")


class RiskAnalysisRequest(BaseModel):
    retrieval_run_id: str | None = Field(
        default=None,
        description="Retrieval run to analyze; defaults to the latest completed retrieval run",
    )
    enable_model_analysis: bool | None = Field(
        default=None,
        description="Override model-assisted analysis for this run",
    )
    enable_validation: bool | None = Field(
        default=None,
        description="Override evidence validation for this run",
    )
    validation_max_retries: int | None = Field(
        default=None,
        ge=0,
        le=5,
        description="Override the bounded correction retry limit for validation",
    )


class RiskAnalysisRunResponse(BaseModel):
    run_id: str = Field(..., description="Risk analysis run identifier")
    document_id: str = Field(..., description="Source document identifier")
    retrieval_run_id: str = Field(..., description="Retrieval run analyzed")
    status: ExtractionRunStatus = Field(..., description="Run lifecycle status")
    provider: str = Field(..., description="LLM provider name")
    model_name: str = Field(..., description="LLM model name")
    clauses_analyzed: int = Field(..., description="Clauses evaluated against policy evidence")
    findings_count: int = Field(..., description="Findings persisted for this run")
    model_analysis_enabled: bool = Field(..., description="Whether model analysis was enabled")
    policy_versions: list[str] = Field(..., description="Policy versions used during analysis")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal analysis warnings")
    error_message: str | None = Field(default=None, description="Fatal run error, if any")
    created_at: str = Field(..., description="ISO 8601 run start timestamp")
    completed_at: str | None = Field(default=None, description="ISO 8601 run completion timestamp")


class RiskFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: str = Field(..., description="Risk finding identifier")
    document_id: str = Field(..., description="Source document identifier")
    clause_id: str | None = Field(default=None, description="Clause that triggered the finding")
    clause_category: str | None = Field(default=None, description="Canonical clause category")
    retrieval_run_id: str = Field(..., description="Retrieval run providing evidence")
    analysis_run_id: str = Field(..., description="Risk analysis run that produced the finding")
    finding_type: FindingType = Field(..., description="Finding classification")
    risk_category: str = Field(..., description="Clause or requirement category implicated")
    severity: RiskPriority = Field(..., description="Review priority from policy rules/config")
    severity_basis: SeverityBasis = Field(
        ..., description="Provenance for the severity (never LLM confidence)"
    )
    rule_id: str | None = Field(default=None, description="Deterministic rule identifier")
    contract_quote: str | None = Field(default=None, description="Verbatim contract excerpt")
    contract_source_reference: str | None = Field(
        default=None, description="Contract citation locator"
    )
    contract_page_number: int | None = Field(
        default=None, description="Page of the cited contract text"
    )
    policy_quote: str | None = Field(default=None, description="Verbatim policy excerpt")
    policy_source_reference: str | None = Field(
        default=None, description="Policy citation locator"
    )
    policy_page_number: int | None = Field(
        default=None, description="Page of the cited policy text"
    )
    policy_id: str | None = Field(default=None, description="Policy that supplied the requirement")
    policy_version: str | None = Field(default=None, description="Policy version at analysis time")
    explanation: str = Field(..., description="Why the finding was raised")
    confidence: float | None = Field(
        default=None, description="Model confidence for model-generated findings only"
    )
    review_status: ReviewStatus = Field(..., description="Human review state")
    validation_status: ValidationStatus = Field(
        default=ValidationStatus.PENDING, description="Independent evidence validation state"
    )
    validation_attempts: int = Field(
        default=0, description="Number of validation checks performed"
    )
    validation_error_categories: list[ValidationErrorCategory] = Field(
        default_factory=list, description="Machine-readable validation failures"
    )
    last_validated_at: str | None = Field(
        default=None, description="ISO 8601 timestamp of the latest validation"
    )
    suggested_question: str = Field(..., description="Question for the reviewer to follow up on")
    analysis_model: str = Field(..., description="Analyzer or model that produced the finding")
    policy_versions: list[str] = Field(
        default_factory=list, description="Policy versions considered in the analysis"
    )
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class RiskAnalysisResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    run: RiskAnalysisRunResponse = Field(..., description="Risk analysis run metadata")
    findings: list[RiskFindingResponse] = Field(..., description="Findings from this run")


class RiskFindingListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total matching findings")
    findings: list[RiskFindingResponse] = Field(..., description="Findings, newest first")


class RiskAnalysisRunListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total risk analysis runs")
    runs: list[RiskAnalysisRunResponse] = Field(..., description="Runs, newest first")
