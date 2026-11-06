from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.db.models import ClauseValidationStatus, ExtractionRunStatus


class ClauseCategory(StrEnum):
    LIABILITY = "liability"
    INDEMNITY = "indemnity"
    TERMINATION = "termination"
    RENEWAL = "renewal"
    PAYMENT = "payment"
    CONFIDENTIALITY = "confidentiality"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    DATA_PROTECTION = "data_protection"
    WARRANTIES = "warranties"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    MISCELLANEOUS = "miscellaneous"


_CATEGORY_ALIASES: dict[str, ClauseCategory] = {
    "liability": ClauseCategory.LIABILITY,
    "limitation_of_liability": ClauseCategory.LIABILITY,
    "limitation of liability": ClauseCategory.LIABILITY,
    "indemnity": ClauseCategory.INDEMNITY,
    "indemnification": ClauseCategory.INDEMNITY,
    "termination": ClauseCategory.TERMINATION,
    "term": ClauseCategory.TERMINATION,
    "term_and_termination": ClauseCategory.TERMINATION,
    "renewal": ClauseCategory.RENEWAL,
    "auto_renewal": ClauseCategory.RENEWAL,
    "renewal_term": ClauseCategory.RENEWAL,
    "payment": ClauseCategory.PAYMENT,
    "fees": ClauseCategory.PAYMENT,
    "payment_terms": ClauseCategory.PAYMENT,
    "billing": ClauseCategory.PAYMENT,
    "confidentiality": ClauseCategory.CONFIDENTIALITY,
    "confidential_information": ClauseCategory.CONFIDENTIALITY,
    "non_disclosure": ClauseCategory.CONFIDENTIALITY,
    "intellectual_property": ClauseCategory.INTELLECTUAL_PROPERTY,
    "intellectual property": ClauseCategory.INTELLECTUAL_PROPERTY,
    "ip": ClauseCategory.INTELLECTUAL_PROPERTY,
    "ip_ownership": ClauseCategory.INTELLECTUAL_PROPERTY,
    "data_protection": ClauseCategory.DATA_PROTECTION,
    "data protection": ClauseCategory.DATA_PROTECTION,
    "data_privacy": ClauseCategory.DATA_PROTECTION,
    "privacy": ClauseCategory.DATA_PROTECTION,
    "gdpr": ClauseCategory.DATA_PROTECTION,
    "warranties": ClauseCategory.WARRANTIES,
    "warranty": ClauseCategory.WARRANTIES,
    "representations_and_warranties": ClauseCategory.WARRANTIES,
    "governing_law": ClauseCategory.GOVERNING_LAW,
    "governing law": ClauseCategory.GOVERNING_LAW,
    "choice_of_law": ClauseCategory.GOVERNING_LAW,
    "dispute_resolution": ClauseCategory.DISPUTE_RESOLUTION,
    "dispute resolution": ClauseCategory.DISPUTE_RESOLUTION,
    "arbitration": ClauseCategory.DISPUTE_RESOLUTION,
    "disputes": ClauseCategory.DISPUTE_RESOLUTION,
    "miscellaneous": ClauseCategory.MISCELLANEOUS,
    "misc": ClauseCategory.MISCELLANEOUS,
    "other": ClauseCategory.MISCELLANEOUS,
}


def normalize_category(value: Any) -> tuple[ClauseCategory, bool]:
    """Map model-provided category text to the canonical enum.

    Returns the category plus whether the original value was recognized.
    Unknown or missing values fall back to miscellaneous and should be flagged.
    """
    if isinstance(value, ClauseCategory):
        return value, True
    if not isinstance(value, str):
        return ClauseCategory.MISCELLANEOUS, False

    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    category = _CATEGORY_ALIASES.get(cleaned)
    if category is not None:
        return category, True

    # Try the normalized enum value directly (e.g. "intellectual_property")
    try:
        return ClauseCategory(cleaned), True
    except ValueError:
        return ClauseCategory.MISCELLANEOUS, False


class ClauseCandidate(BaseModel):
    """Lenient model for a single clause returned by an LLM.

    Unknown fields are ignored and partial output is accepted so the service can
    validate citations and flag incomplete candidates instead of failing the run.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    category: str | None = Field(default=None)
    source_text: str = Field(
        default="",
        validation_alias=AliasChoices(
            "source_text",
            "exact_source_text",
            "exact_text",
            "quote",
            "text",
        ),
    )
    summary: str | None = Field(
        default=None,
        validation_alias=AliasChoices("summary", "normalized_summary", "concise_summary"),
    )
    page_number: int | None = Field(
        default=None,
        validation_alias=AliasChoices("page_number", "page"),
    )
    section_heading: str | None = Field(
        default=None,
        validation_alias=AliasChoices("section_heading", "section", "heading"),
    )
    start_char_offset: int | None = Field(
        default=None,
        validation_alias=AliasChoices("start_char_offset", "start_offset", "char_start"),
    )
    end_char_offset: int | None = Field(
        default=None,
        validation_alias=AliasChoices("end_char_offset", "end_offset", "char_end"),
    )
    source_chunk_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("source_chunk_id", "chunk_id", "citation"),
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("source_text", "summary", "section_heading", "source_chunk_id", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return str(value)
        return value

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("high", "very high"):
                return 0.9
            if normalized == "medium":
                return 0.6
            if normalized in ("low", "very low"):
                return 0.3
            try:
                return float(normalized.rstrip("%")) / (
                    100.0 if normalized.endswith("%") else 1.0
                )
            except ValueError:
                return None
        return value

    @field_validator("page_number", "start_char_offset", "end_char_offset", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return None
        return value


class ClauseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clause_id: str = Field(..., description="Deterministic clause identifier")
    document_id: str = Field(..., description="Source document identifier")
    extraction_run_id: str = Field(..., description="Extraction run that produced this clause")
    category: ClauseCategory = Field(..., description="Canonical clause category")
    source_text: str = Field(..., description="Exact verbatim source wording")
    normalized_summary: str = Field(..., description="Model-generated concise summary")
    page_number: int | None = Field(default=None, description="1-indexed source page")
    section_heading: str | None = Field(default=None, description="Source section heading")
    start_char_offset: int | None = Field(
        default=None, description="Start offset in the reconstructed document text"
    )
    end_char_offset: int | None = Field(
        default=None, description="End offset in the reconstructed document text"
    )
    confidence: float | None = Field(default=None, description="Extraction confidence (0.0-1.0)")
    validation_status: ClauseValidationStatus = Field(
        ..., description="Validation outcome for the clause citation"
    )
    validation_notes: str | None = Field(
        default=None, description="Human-readable validation notes"
    )
    source_chunk_ids: list[str] = Field(
        default_factory=list, description="Document chunk identifiers covering the citation"
    )
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class ExtractionRunResponse(BaseModel):
    run_id: str = Field(..., description="Extraction run identifier")
    document_id: str = Field(..., description="Source document identifier")
    status: ExtractionRunStatus = Field(..., description="Run lifecycle status")
    provider: str = Field(..., description="LLM provider name")
    model_name: str = Field(..., description="LLM model name")
    total_chunks: int = Field(..., description="Bounded extraction chunks processed")
    candidates_received: int = Field(..., description="Raw clause candidates returned by the model")
    clauses_persisted: int = Field(..., description="Validated, deduplicated clauses persisted")
    duplicates_merged: int = Field(..., description="Duplicate candidates merged deterministically")
    candidates_rejected: int = Field(..., description="Candidates rejected for invalid citations")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal extraction warnings")
    error_message: str | None = Field(default=None, description="Fatal run error, if any")
    created_at: str = Field(..., description="ISO 8601 run start timestamp")
    completed_at: str | None = Field(default=None, description="ISO 8601 run completion timestamp")


class ClauseExtractionResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    run: ExtractionRunResponse = Field(..., description="Extraction run metadata")
    clauses: list[ClauseResponse] = Field(..., description="Validated clauses from this run")


class ClauseListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total matching clauses")
    clauses: list[ClauseResponse] = Field(..., description="Clauses ordered by source offset")


class ExtractionRunListResponse(BaseModel):
    document_id: str = Field(..., description="Source document identifier")
    total: int = Field(..., description="Total extraction runs")
    runs: list[ExtractionRunResponse] = Field(..., description="Extraction runs, newest first")
