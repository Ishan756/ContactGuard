from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.db.models import Document, DocumentChunk
from app.db.session import get_db
from app.schemas.document import (
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentMetadataResponse,
    DocumentTextResponse,
    DocumentUploadResponse,
)
from app.services.ingestion.service import DocumentIngestionService
from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_ingestion_service(
    storage: StorageBackend = Depends(get_storage_backend),
    settings: Settings = Depends(get_settings),
) -> DocumentIngestionService:
    return DocumentIngestionService(storage=storage, settings=settings)


def format_iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def map_document_metadata(doc: Document) -> DocumentMetadataResponse:
    return DocumentMetadataResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_size_bytes=doc.file_size_bytes,
        mime_type=doc.mime_type,
        file_hash_sha256=doc.file_hash_sha256,
        status=doc.status,
        error_message=doc.error_message,
        total_pages=doc.total_pages,
        total_characters=doc.total_characters,
        created_at=format_iso(doc.created_at),
        updated_at=format_iso(doc.updated_at),
    )


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest contract document",
    description="Uploads a PDF or DOCX contract, performs security verification, extracts page-aware chunks, and persists metadata.",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF or DOCX contract file"),
    db: AsyncSession = Depends(get_db),
    ingestion_service: DocumentIngestionService = Depends(get_ingestion_service),
) -> DocumentUploadResponse:
    document = await ingestion_service.ingest_document(upload_file=file, db=db)

    # Count chunks
    chunk_count_stmt = select(func.count(DocumentChunk.id)).where(
        DocumentChunk.document_id == document.id
    )
    chunk_count = (await db.execute(chunk_count_stmt)).scalar() or 0

    message = (
        "Document successfully ingested and parsed."
        if document.status == "completed"
        else f"Ingestion completed with status '{document.status}': {document.error_message or ''}"
    )

    return DocumentUploadResponse(
        document=map_document_metadata(document),
        chunks_extracted=chunk_count,
        message=message,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all uploaded contract documents",
)
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    total_stmt = select(func.count(Document.id))
    total = (await db.execute(total_stmt)).scalar() or 0

    stmt = select(Document).order_by(Document.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    docs = result.scalars().all()

    return DocumentListResponse(
        documents=[map_document_metadata(d) for d in docs],
        total=total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentMetadataResponse,
    summary="Get document metadata and status",
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> DocumentMetadataResponse:
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise NotFoundError(f"Document with ID '{document_id}' not found.")

    return map_document_metadata(document)


@router.get(
    "/{document_id}/chunks",
    response_model=DocumentTextResponse,
    summary="Retrieve extracted text chunks with pagination",
    description="Returns page-aware bounded text chunks with stable source locators and heading context.",
)
async def get_document_chunks(
    document_id: str,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Chunks per page"),
    db: AsyncSession = Depends(get_db),
) -> DocumentTextResponse:
    # Verify document exists
    doc_stmt = select(Document).where(Document.id == document_id)
    doc_res = await db.execute(doc_stmt)
    doc = doc_res.scalar_one_or_none()
    if not doc:
        raise NotFoundError(f"Document with ID '{document_id}' not found.")

    # Count total chunks
    count_stmt = select(func.count(DocumentChunk.id)).where(
        DocumentChunk.document_id == document_id
    )
    total_chunks = (await db.execute(count_stmt)).scalar() or 0

    offset = (page - 1) * page_size
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    chunk_responses = [
        DocumentChunkResponse(
            id=c.id,
            document_id=c.document_id,
            page_number=c.page_number,
            section_heading=c.section_heading,
            chunk_index=c.chunk_index,
            text=c.text,
            start_char_offset=c.start_char_offset,
            end_char_offset=c.end_char_offset,
            source_identifier=c.source_identifier,
        )
        for c in chunks
    ]

    has_more = (offset + len(chunks)) < total_chunks

    return DocumentTextResponse(
        document_id=document_id,
        total_chunks=total_chunks,
        page=page,
        page_size=page_size,
        has_more=has_more,
        chunks=chunk_responses,
    )


@router.get(
    "/{document_id}/text",
    response_model=DocumentTextResponse,
    summary="Alias for document chunks retrieval",
)
async def get_document_text(
    document_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> DocumentTextResponse:
    return await get_document_chunks(document_id=document_id, page=page, page_size=page_size, db=db)
