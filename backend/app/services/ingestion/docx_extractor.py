import io

import docx

from app.core.logging import get_logger
from app.db.models import DocumentStatus
from app.services.ingestion.base import DocumentExtractor, ExtractedChunk, ExtractionResult

logger = get_logger("contractguard.ingestion.docx")


class DOCXExtractor(DocumentExtractor):
    """Secure DOCX text extractor preserving paragraph structure, headings, and character offsets."""

    def extract(self, content: bytes, document_id: str) -> ExtractionResult:
        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception as exc:
            logger.warning("Failed to open DOCX stream for doc %s: %s", document_id, exc)
            return ExtractionResult(
                total_pages=0,
                total_characters=0,
                status=DocumentStatus.FAILED,
                error_message=f"Malformed or unreadable DOCX document: {exc}",
            )

        chunks: list[ExtractedChunk] = []
        running_char_count = 0
        current_heading: str | None = None
        current_page = 1
        page_char_count = 0
        chunk_idx = 0

        # Iterate over all paragraphs
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Check if paragraph has heading style
            style_name = para.style.name.lower() if para.style and para.style.name else ""
            if "heading" in style_name or "title" in style_name:
                current_heading = text
            elif len(text) < 80 and (
                text.isupper()
                or text.startswith(("ARTICLE", "SECTION", "1.", "2.", "3.", "4.", "5."))
            ):
                current_heading = text

            start_offset = page_char_count
            end_offset = page_char_count + len(text)
            page_char_count = end_offset + 1
            running_char_count += len(text)

            # Heuristic page estimation (~2500 characters per page if no hard page break)
            if page_char_count > 2500:
                current_page += 1
                page_char_count = 0

            chunks.append(
                ExtractedChunk(
                    page_number=current_page,
                    section_heading=current_heading,
                    text=text,
                    start_char_offset=start_offset,
                    end_char_offset=end_offset,
                    chunk_index=chunk_idx,
                )
            )
            chunk_idx += 1

        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_cells_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if not row_cells_text:
                    continue
                row_str = " | ".join(row_cells_text)
                start_offset = page_char_count
                end_offset = page_char_count + len(row_str)
                page_char_count = end_offset + 1
                running_char_count += len(row_str)

                chunks.append(
                    ExtractedChunk(
                        page_number=current_page,
                        section_heading=current_heading or "Table Content",
                        text=row_str,
                        start_char_offset=start_offset,
                        end_char_offset=end_offset,
                        chunk_index=chunk_idx,
                    )
                )
                chunk_idx += 1

        if running_char_count == 0:
            return ExtractionResult(
                total_pages=0,
                total_characters=0,
                chunks=[],
                status=DocumentStatus.FAILED,
                error_message="Document is empty or contains no readable text content.",
            )

        return ExtractionResult(
            total_pages=current_page,
            total_characters=running_char_count,
            chunks=chunks,
            status=DocumentStatus.COMPLETED,
            error_message=None,
        )
