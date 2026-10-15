from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.db.models import DocumentStatus


@dataclass
class ExtractedChunk:
    page_number: int
    section_heading: str | None
    text: str
    start_char_offset: int
    end_char_offset: int
    chunk_index: int


@dataclass
class ExtractionResult:
    total_pages: int
    total_characters: int
    chunks: list[ExtractedChunk] = field(default_factory=list)
    status: DocumentStatus = DocumentStatus.COMPLETED
    error_message: str | None = None


class DocumentExtractor(ABC):
    """Abstract interface for file-format specific text and heading extraction."""

    @abstractmethod
    def extract(self, content: bytes, document_id: str) -> ExtractionResult:
        """Parse bytes and extract page-aware sections with offsets."""
        pass
