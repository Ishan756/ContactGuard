from pydantic import BaseModel, ConfigDict, Field

from app.db.models import (
    ClauseChangeType,
    ComparisonStatus,
    FindingChangeType,
)


class ContractComparisonRequest(BaseModel):
    base_document_id: str = Field(..., description="Earlier contract version document identifier")
    target_document_id: str = Field(..., description="Newer contract version document identifier")
    reanalyze_target: bool = Field(
        default=False,
        description=(
            "When true, re-run risk analysis on the newer version for matched clauses that "
            "changed. Existing analysis history is preserved."
        ),
    )


class ClauseChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_id: str
    change_type: ClauseChangeType
    category: str
    base_clause_id: str | None = None
    target_clause_id: str | None = None
    base_category: str | None = None
    target_category: str | None = None
    base_source_text: str | None = None
    target_source_text: str | None = None
    base_source_reference: str | None = None
    target_source_reference: str | None = None
    similarity: float
    change_summary: str
    created_at: str


class FindingChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_id: str
    change_type: FindingChangeType
    finding_type: str
    risk_category: str
    rule_id: str | None = None
    base_finding_id: str | None = None
    target_finding_id: str | None = None
    base_severity: str | None = None
    target_severity: str | None = None
    base_validation_status: str | None = None
    target_validation_status: str | None = None
    contract_source_reference: str | None = None
    explanation: str
    created_at: str


class ContractComparisonResponse(BaseModel):
    comparison_id: str
    base_document_id: str
    target_document_id: str
    created_by: str
    status: ComparisonStatus
    base_analysis_run_id: str | None = None
    target_analysis_run_id: str | None = None
    clauses_added: int
    clauses_removed: int
    clauses_modified: int
    clauses_unchanged: int
    clauses_reclassified: int
    findings_new: int
    findings_resolved: int
    findings_persisted: int
    findings_severity_changed: int
    affected_clause_ids: list[str] = Field(default_factory=list)
    reanalysis_requested: bool
    reanalysis_performed: bool
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None
    clause_changes: list[ClauseChangeResponse] = Field(default_factory=list)
    finding_changes: list[FindingChangeResponse] = Field(default_factory=list)
    notice: str = (
        "Version comparison identifies textual and finding-level changes. It is not a legal "
        "opinion and does not determine enforceability."
    )


class ContractComparisonListResponse(BaseModel):
    comparisons: list[ContractComparisonResponse]
    total: int
