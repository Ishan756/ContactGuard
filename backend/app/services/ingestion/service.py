import hashlib
import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppException, ValidationError
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus
from app.services.ingestion.base import ExtractionResult
from app.services.ingestion.docx_extractor import DOCXExtractor
from app.services.ingestion.pdf_extractor import PDFExtractor
from app.storage.base import StorageBackend

logger = get_logger("contractguard.ingestion.service")


class DocumentIngestionService:
    """Orchestrates security validation, storage persistence, and text extraction."""

    def __init__(self, storage: StorageBackend, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings
        self.pdf_extractor = PDFExtractor()
        self.docx_extractor = DOCXExtractor()

    def sanitize_filename(self, filename: str) -> str:
        """Sanitize original filename against directory traversal and dangerous characters."""
        base_name = Path(filename).name
        # Keep alphanumeric, spaces, dots, hyphens, and underscores
        cleaned = re.sub(r"[^\w\s.-]", "", base_name).strip()
        # Collapse multi spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned or f"contract_{uuid.uuid4().hex[:8]}"

    def validate_content_signature(self, content: bytes, extension: str) -> None:
        """Verify that file header magic bytes match the claimed format."""
        if extension == "pdf":
            if not content.startswith(b"%PDF-"):
                raise ValidationError("File content does not match valid PDF signature (%PDF-).")
        elif extension == "docx":
            if not content.startswith(b"PK\x03\x04"):
                raise ValidationError("File content does not match valid DOCX archive signature.")

    async def ingest_document(
        self,
        upload_file: UploadFile,
        db: AsyncSession,
    ) -> Document:
        """Perform comprehensive document ingestion, validation, storage, and extraction."""
        original_name = upload_file.filename or "unknown_document"
        sanitized_name = self.sanitize_filename(original_name)

        # 1. Extension Check
        extension = Path(sanitized_name).suffix.lstrip(".").lower()
        if extension not in self.settings.allowed_extensions:
            raise ValidationError(
                f"Unsupported file format '{extension}'. Allowed formats: {', '.join(self.settings.allowed_extensions)}"
            )

        # 2. Read content safely with size limit checking
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        content = await upload_file.read()

        # 3. Empty Document Check
        if not content or len(content) == 0:
            raise ValidationError("Uploaded file is empty (0 bytes).")

        # 4. File Size Check
        if len(content) > max_bytes:
            raise AppException(
                f"File size ({len(content) / (1024 * 1024):.2f}MB) exceeds maximum allowed limit of {self.settings.max_upload_size_mb}MB.",
                code="FILE_TOO_LARGE",
                status_code=413,
            )

        # 5. Magic Bytes Security Validation
        self.validate_content_signature(content, extension)

        # 6. Integrity Hash
        sha256_hash = hashlib.sha256(content).hexdigest()

        # 7. Generate Server-Side Identifier and Store Raw Content
        document_id = str(uuid.uuid4())
        try:
            stored_path = await self.storage.save_file(
                file_id=document_id,
                content=content,
                extension=extension,
            )
        except Exception as exc:
            logger.error("Failed to persist file %s to storage: %s", document_id, exc)
            raise AppException(
                f"Failed to persist document to storage: {exc}", code="STORAGE_ERROR"
            )

        mime_type = upload_file.content_type or (
            "application/pdf"
            if extension == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        # 8. Create Database Record
        doc_record = Document(
            id=document_id,
            original_filename=sanitized_name,
            stored_path=stored_path,
            file_size_bytes=len(content),
            mime_type=mime_type,
            file_hash_sha256=sha256_hash,
            status=DocumentStatus.PROCESSING,
            total_pages=0,
            total_characters=0,
        )
        db.add(doc_record)
        await db.flush()

        # 9. Perform Text and Heading Extraction
        result: ExtractionResult
        if extension == "pdf":
            result = self.pdf_extractor.extract(content, document_id)
        else:
            result = self.docx_extractor.extract(content, document_id)

        # 10. Update Document Status & Persist Chunks
        doc_record.status = result.status
        doc_record.error_message = result.error_message
        doc_record.total_pages = result.total_pages
        doc_record.total_characters = result.total_characters

        if result.chunks:
            for c in result.chunks:
                source_id = f"doc:{document_id}:p{c.page_number}:c{c.chunk_index}"
                chunk_record = DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    page_number=c.page_number,
                    section_heading=c.section_heading,
                    chunk_index=c.chunk_index,
                    text=c.text,
                    start_char_offset=c.start_char_offset,
                    end_char_offset=c.end_char_offset,
                    source_identifier=source_id,
                    is_trusted_system_instruction=False,
                )
                db.add(chunk_record)

        await db.commit()
        await db.refresh(doc_record)

        logger.info(
            "Ingestion completed for doc %s ('%s'): status=%s, pages=%s, chunks=%s, chars=%s",
            document_id,
            sanitized_name,
            doc_record.status,
            doc_record.total_pages,
            len(result.chunks),
            doc_record.total_characters,
        )

        return doc_record
