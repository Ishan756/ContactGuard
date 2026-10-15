from pydantic import BaseModel, ConfigDict, Field

from app.db.models import DocumentStatus


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique chunk UUID")
    document_id: str = Field(..., description="Parent document UUID")
    page_number: int = Field(..., description="1-indexed source document page")
    section_heading: str | None = Field(default=None, description="Extracted section/clause header")
    chunk_index: int = Field(..., description="0-indexed position within document sequence")
    text: str = Field(..., description="Extracted textual content")
    start_char_offset: int = Field(..., description="Start character offset within page/section")
    end_char_offset: int = Field(..., description="End character offset within page/section")
    source_identifier: str = Field(..., description="Stable location locator e.g. doc-id:p1:c0")


class DocumentMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique document UUID")
    original_filename: str = Field(..., description="Sanitized original document filename")
    file_size_bytes: int = Field(..., description="File size in bytes")
    mime_type: str = Field(..., description="MIME content type")
    file_hash_sha256: str = Field(..., description="SHA-256 integrity hash")
    status: DocumentStatus = Field(..., description="Current processing lifecycle status")
    error_message: str | None = Field(default=None, description="Diagnostic error or OCR guidance")
    total_pages: int = Field(..., description="Total pages detected")
    total_characters: int = Field(..., description="Total characters extracted")
    created_at: str = Field(..., description="ISO 8601 upload timestamp")
    updated_at: str = Field(..., description="ISO 8601 status update timestamp")


class DocumentUploadResponse(BaseModel):
    document: DocumentMetadataResponse = Field(..., description="Document metadata")
    chunks_extracted: int = Field(..., description="Number of text chunks extracted")
    message: str = Field(..., description="Status summary message")


class DocumentTextResponse(BaseModel):
    document_id: str = Field(..., description="Parent document identifier")
    total_chunks: int = Field(..., description="Total available chunks")
    page: int = Field(..., description="Current pagination page (1-indexed)")
    page_size: int = Field(..., description="Chunks per page")
    has_more: bool = Field(..., description="True if further chunks exist")
    chunks: list[DocumentChunkResponse] = Field(..., description="Extracted bounded chunks")


class DocumentListResponse(BaseModel):
    documents: list[DocumentMetadataResponse] = Field(..., description="List of stored documents")
    total: int = Field(..., description="Total document count")
