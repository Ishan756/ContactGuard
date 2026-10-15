import re

import fitz  # PyMuPDF

from app.core.logging import get_logger
from app.db.models import DocumentStatus
from app.services.ingestion.base import DocumentExtractor, ExtractedChunk, ExtractionResult

logger = get_logger("contractguard.ingestion.pdf")

# Regex to identify typical legal contract headings (e.g., "1. Definitions", "ARTICLE IV - INDEMNITY", "Section 3. Term")
HEADING_PATTERN = re.compile(
    r"^((ARTICLE|SECTION|CLAUSE)\s+([0-9IVXLCDM]+|[A-Z])[\s.:-]|([0-9]{1,2}\.?\s+[A-Z][a-zA-Z\s]{2,50}))",
    re.IGNORECASE,
)


class PDFExtractor(DocumentExtractor):
    """Secure PDF text extractor preserving page indices, headings, and character offsets."""

    def extract(self, content: bytes, document_id: str) -> ExtractionResult:
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            logger.warning("Failed to open PDF stream for doc %s: %s", document_id, exc)
            return ExtractionResult(
                total_pages=0,
                total_characters=0,
                status=DocumentStatus.FAILED,
                error_message=f"Malformed or unreadable PDF document: {exc}",
            )

        # 1. Check for PDF Encryption
        if doc.is_encrypted:
            # Attempt to authenticate with blank password (some PDFs are encrypted with empty password)
            if not doc.authenticate(""):
                doc.close()
                return ExtractionResult(
                    total_pages=0,
                    total_characters=0,
                    status=DocumentStatus.FAILED,
                    error_message="Encrypted PDF document cannot be parsed without password.",
                )

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            return ExtractionResult(
                total_pages=0,
                total_characters=0,
                status=DocumentStatus.FAILED,
                error_message="PDF contains zero pages.",
            )

        chunks: list[ExtractedChunk] = []
        running_char_count = 0
        current_heading: str | None = None
        has_images = False
        chunk_idx = 0

        for page_idx in range(total_pages):
            page_number = page_idx + 1
            page = doc[page_idx]

            # Check if page has embedded images
            image_list = page.get_images()
            if image_list:
                has_images = True

            # Extract structured blocks: (x0, y0, x1, y1, text, block_no, block_type)
            # block_type 0 = text, 1 = image
            blocks = page.get_text("blocks")
            page_offset = 0

            for b in blocks:
                if len(b) >= 5 and b[6] == 0:  # text block
                    block_text = b[4].strip()
                    if not block_text:
                        continue

                    # Check if block looks like a contract section heading
                    first_line = block_text.splitlines()[0].strip()
                    if len(first_line) < 80 and (
                        HEADING_PATTERN.match(first_line)
                        or (first_line.isupper() and len(first_line) > 3)
                    ):
                        current_heading = first_line

                    start_offset = page_offset
                    end_offset = page_offset + len(block_text)
                    page_offset = end_offset + 1
                    running_char_count += len(block_text)

                    chunks.append(
                        ExtractedChunk(
                            page_number=page_number,
                            section_heading=current_heading,
                            text=block_text,
                            start_char_offset=start_offset,
                            end_char_offset=end_offset,
                            chunk_index=chunk_idx,
                        )
                    )
                    chunk_idx += 1

        doc.close()

        # 2. Check for Scanned / Image-Only PDFs
        if running_char_count < 50 and (has_images or total_pages > 0):
            return ExtractionResult(
                total_pages=total_pages,
                total_characters=running_char_count,
                chunks=chunks,
                status=DocumentStatus.NEEDS_OCR,
                error_message="Scanned document detected with minimal extractable text. OCR is required to extract contract clauses.",
            )

        # 3. Check for Empty Document
        if running_char_count == 0:
            return ExtractionResult(
                total_pages=total_pages,
                total_characters=0,
                chunks=[],
                status=DocumentStatus.FAILED,
                error_message="Document is empty or contains no extractable text.",
            )

        return ExtractionResult(
            total_pages=total_pages,
            total_characters=running_char_count,
            chunks=chunks,
            status=DocumentStatus.COMPLETED,
            error_message=None,
        )
