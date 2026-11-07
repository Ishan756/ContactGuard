import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    REVISING = "revising"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowEventType(StrEnum):
    STARTED = "started"
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    INTERRUPTED = "interrupted"
    RESUMED = "resumed"
    REVIEW_DECISION = "review_decision"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewDecisionType(StrEnum):
    APPROVE = "approve"
    DISMISS = "dismiss"
    REQUEST_REVISION = "request_revision"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_OCR = "needs_ocr"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=DocumentStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    total_characters: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
    extraction_runs: Mapped[list["ClauseExtractionRun"]] = relationship(
        "ClauseExtractionRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ClauseExtractionRun.created_at",
    )
    clauses: Mapped[list["Clause"]] = relationship(
        "Clause",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Clause.start_char_offset",
    )
    policy_retrieval_runs: Mapped[list["PolicyRetrievalRun"]] = relationship(
        "PolicyRetrievalRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="PolicyRetrievalRun.created_at",
    )
    risk_analysis_runs: Mapped[list["RiskAnalysisRun"]] = relationship(
        "RiskAnalysisRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="RiskAnalysisRun.created_at",
    )
    risk_findings: Mapped[list["RiskFinding"]] = relationship(
        "RiskFinding",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="RiskFinding.created_at",
    )
    evidence_validation_runs: Mapped[list["EvidenceValidationRun"]] = relationship(
        "EvidenceValidationRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="EvidenceValidationRun.created_at",
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="WorkflowRun.created_at",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(100), nullable=False)

    # Security flag enforcing that extracted text is never executed as LLM system commands
    is_trusted_system_instruction: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=PolicyStatus.ACTIVE, index=True)

    # Relationship to source document if uploaded as PDF/DOCX
    source_document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )

    total_chunks: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    chunks: Mapped[list["PolicyChunk"]] = relationship(
        "PolicyChunk",
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyChunk.chunk_index",
    )


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_char_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    vector_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    policy: Mapped["Policy"] = relationship("Policy", back_populates="chunks")


class ExtractionRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ClauseValidationStatus(StrEnum):
    VALID = "valid"
    NEEDS_REVIEW = "needs_review"


class ClauseExtractionRun(Base):
    __tablename__ = "clause_extraction_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ExtractionRunStatus.RUNNING
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clauses_persisted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_merged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="extraction_runs")
    clauses: Mapped[list["Clause"]] = relationship(
        "Clause",
        back_populates="extraction_run",
        cascade="all, delete-orphan",
        order_by="Clause.start_char_offset",
    )


class Clause(Base):
    __tablename__ = "clauses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extraction_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("clause_extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_summary: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_char_offset: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    end_char_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ClauseValidationStatus.VALID
    )
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chunk_ids: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="clauses")
    extraction_run: Mapped["ClauseExtractionRun"] = relationship(
        "ClauseExtractionRun", back_populates="clauses"
    )


class PolicyRetrievalRun(Base):
    __tablename__ = "policy_retrieval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ExtractionRunStatus.RUNNING
    )
    embedding_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    clauses_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    missing_coverage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    policy_statuses: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_versions: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="policy_retrieval_runs"
    )
    evidence: Mapped[list["PolicyRetrievalEvidence"]] = relationship(
        "PolicyRetrievalEvidence",
        back_populates="retrieval_run",
        cascade="all, delete-orphan",
        order_by="PolicyRetrievalEvidence.rank",
    )


class PolicyRetrievalEvidence(Base):
    __tablename__ = "policy_retrieval_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policy_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clause_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    policy_name: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_status: Mapped[str] = mapped_column(String(30), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_char_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_char_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    retrieval_run: Mapped["PolicyRetrievalRun"] = relationship(
        "PolicyRetrievalRun", back_populates="evidence"
    )


class RiskAnalysisRun(Base):
    __tablename__ = "risk_analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policy_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ExtractionRunStatus.RUNNING
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    clauses_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    policy_versions: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="risk_analysis_runs")
    findings: Mapped[list["RiskFinding"]] = relationship(
        "RiskFinding",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        order_by="RiskFinding.created_at",
    )
    validation_runs: Mapped[list["EvidenceValidationRun"]] = relationship(
        "EvidenceValidationRun",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
        order_by="EvidenceValidationRun.created_at",
    )


class RiskFinding(Base):
    __tablename__ = "risk_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    clause_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("clauses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    clause_category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policy_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("risk_analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    risk_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    contract_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    policy_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    policy_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False)
    suggested_question: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_model: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_versions: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    policy_page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    validation_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    validation_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_error_categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    document: Mapped["Document"] = relationship("Document", back_populates="risk_findings")
    analysis_run: Mapped["RiskAnalysisRun"] = relationship(
        "RiskAnalysisRun", back_populates="findings"
    )
    validation_attempt_records: Mapped[list["EvidenceValidationAttempt"]] = relationship(
        "EvidenceValidationAttempt",
        back_populates="finding",
        cascade="all, delete-orphan",
        order_by="EvidenceValidationAttempt.created_at",
    )


class EvidenceValidationRun(Base):
    __tablename__ = "evidence_validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("risk_analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("policy_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ExtractionRunStatus.RUNNING
    )
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    findings_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unverified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inconclusive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retries_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="evidence_validation_runs")
    analysis_run: Mapped["RiskAnalysisRun"] = relationship(
        "RiskAnalysisRun", back_populates="validation_runs"
    )
    attempts: Mapped[list["EvidenceValidationAttempt"]] = relationship(
        "EvidenceValidationAttempt",
        back_populates="validation_run",
        cascade="all, delete-orphan",
        order_by="EvidenceValidationAttempt.created_at",
    )


class EvidenceValidationAttempt(Base):
    __tablename__ = "evidence_validation_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    validation_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evidence_validation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("risk_findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    retry_target: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    error_categories: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_error_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    validation_run: Mapped["EvidenceValidationRun"] = relationship(
        "EvidenceValidationRun", back_populates="attempts"
    )
    finding: Mapped["RiskFinding"] = relationship(
        "RiskFinding", back_populates="validation_attempt_records"
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=WorkflowStatus.PENDING, index=True
    )
    current_node: Mapped[str | None] = mapped_column(String(80), nullable=True)
    interrupted_node: Mapped[str | None] = mapped_column(String(80), nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    models_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    clause_extraction_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    policy_retrieval_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    risk_analysis_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    validation_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_report: Mapped[str | None] = mapped_column(Text, nullable=True)
    state_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="workflow_runs")
    events: Mapped[list["WorkflowEvent"]] = relationship(
        "WorkflowEvent",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        order_by="WorkflowEvent.created_at",
    )
    decisions: Mapped[list["ReviewDecision"]] = relationship(
        "ReviewDecision",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        order_by="ReviewDecision.created_at",
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    node: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status_from: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="events"
    )


class ReviewDecision(Base):
    """Append-only reviewer decision record; rows are never updated or deleted."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    finding_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_target: Mapped[str | None] = mapped_column(String(20), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="decisions"
    )
