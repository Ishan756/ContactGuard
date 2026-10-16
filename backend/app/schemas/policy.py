from pydantic import BaseModel, ConfigDict, Field
from app.db.models import PolicyStatus


class PolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255, description="Name of company policy")
    version: str = Field(default="1.0.0", description="Semantic policy version")
    category: str | None = Field(default=None, description="Policy domain (e.g. Legal, Compliance, Financial)")
    description: str | None = Field(default=None, description="Overview of policy purpose")
    text_content: str | None = Field(
        default=None,
        description="Raw policy body text if creating directly without a document upload",
    )


class PolicyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    version: str | None = Field(default=None)
    category: str | None = Field(default=None)
    description: str | None = Field(default=None)
    status: PolicyStatus | None = Field(default=None)
    text_content: str | None = Field(default=None, description="Updated policy content to re-index")


class PolicyChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Chunk UUID")
    policy_id: str = Field(..., description="Parent policy UUID")
    chunk_index: int = Field(..., description="Sequence index")
    section_heading: str | None = Field(default=None, description="Section heading")
    page_number: int = Field(default=1, description="Page number")
    start_char_offset: int = Field(..., description="Start character offset")
    end_char_offset: int = Field(..., description="End character offset")
    text: str = Field(..., description="Chunk body text")
    source_identifier: str = Field(..., description="Stable citation identifier")


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Policy UUID")
    name: str = Field(..., description="Policy name")
    version: str = Field(..., description="Policy version")
    category: str | None = Field(default=None, description="Domain category")
    description: str | None = Field(default=None, description="Description")
    status: PolicyStatus = Field(..., description="Policy status")
    source_document_id: str | None = Field(default=None, description="Source document ID if ingested via file")
    total_chunks: int = Field(..., description="Total vector-indexed chunks")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 update timestamp")


class PolicyListResponse(BaseModel):
    policies: list[PolicyResponse] = Field(..., description="List of policies")
    total: int = Field(..., description="Total policy count")


class PolicySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Contract clause or query text to audit against policy")
    policy_id: str | None = Field(default=None, description="Filter to a specific policy ID")
    category: str | None = Field(default=None, description="Filter by policy domain category")
    limit: int = Field(default=5, ge=1, le=20, description="Max policy passages to retrieve")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum cosine similarity threshold")


class PolicySearchResultItem(BaseModel):
    chunk_id: str = Field(..., description="Stable chunk identifier")
    source_identifier: str = Field(..., description="Citation locator e.g. pol:uuid:p1:c0")
    policy_id: str = Field(..., description="Parent policy ID")
    policy_name: str = Field(..., description="Parent policy name")
    policy_version: str = Field(..., description="Policy version")
    category: str | None = Field(default=None, description="Domain category")
    section_heading: str | None = Field(default=None, description="Section heading")
    page_number: int = Field(..., description="Source page number")
    start_char_offset: int = Field(..., description="Start character offset")
    end_char_offset: int = Field(..., description="End character offset")
    text: str = Field(..., description="Policy rule text passage")
    similarity_score: float = Field(..., description="Cosine similarity score (0.0 - 1.0)")
    factual_confidence_note: str = Field(
        default="Similarity score indicates semantic closeness, not factual legal compliance.",
        description="Notice distinguishing similarity from factual certainty",
    )


class PolicySearchResponse(BaseModel):
    query: str = Field(..., description="Searched clause or prompt text")
    total_results: int = Field(..., description="Number of passages retrieved")
    model_used: str = Field(..., description="Embedding model name utilized")
    dimension: int = Field(..., description="Vector dimensionality")
    results: list[PolicySearchResultItem] = Field(..., description="Ranked policy passages")
