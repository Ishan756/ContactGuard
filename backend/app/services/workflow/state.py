from typing import Any, TypedDict


class WorkflowState(TypedDict, total=False):
    """Typed, intentionally compact shared state for LangGraph transitions.

    Full contract text and full policy passages remain in PostgreSQL/Qdrant; the graph
    carries identifiers, compact summaries, outcomes, and run metadata only.
    """

    workflow_id: str
    thread_id: str
    document_id: str
    owner_reviewer_id: str
    workflow_status: str
    step_count: int
    retry_count: int
    revision_count: int
    max_retries: int
    max_steps: int
    enable_model_analysis: bool

    clause_extraction_run_id: str | None
    policy_retrieval_run_id: str | None
    risk_analysis_run_id: str | None
    validation_run_id: str | None

    clauses: list[dict[str, Any]]
    retrieved_evidence: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    validation: dict[str, Any]

    retrieval_missing_coverage_count: int
    retry_target: str
    missing_evidence: bool
    review_required: bool

    errors: list[dict[str, Any]]
    warnings: list[str]
    failed_node: str | None

    review_request: dict[str, Any] | None
    review_report: dict[str, Any] | None
    review_decision: dict[str, Any] | None

    run_metadata: dict[str, Any]
