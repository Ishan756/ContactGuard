from dataclasses import dataclass
import re

HEADING_REGEX = re.compile(
    r"^((ARTICLE|SECTION|CLAUSE|POLICY)\s+([0-9IVXLCDM]+|[A-Z])[\s.:-]|([0-9]{1,2}\.?\s+[A-Z][a-zA-Z\s]{2,60}))",
    re.IGNORECASE,
)


@dataclass
class PolicyChunkData:
    chunk_index: int
    text: str
    section_heading: str | None
    page_number: int
    start_char_offset: int
    end_char_offset: int


class PolicyChunker:
    """Intelligent policy chunker breaking legal text by paragraphs and section boundaries with overlap."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(
        self,
        full_text: str,
        initial_page: int = 1,
        initial_heading: str | None = None,
    ) -> list[PolicyChunkData]:
        if not full_text or not full_text.strip():
            return []

        paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in full_text.splitlines() if p.strip()]

        chunks: list[PolicyChunkData] = []
        current_chunk_words: list[str] = []
        current_chunk_len = 0
        current_heading = initial_heading
        chunk_idx = 0
        running_char_offset = 0

        for para in paragraphs:
            # Check if paragraph represents a new section or policy rule heading
            first_line = para.splitlines()[0].strip()
            if len(first_line) < 80 and (
                HEADING_REGEX.match(first_line)
                or (first_line.isupper() and len(first_line) > 3)
            ):
                # If we already have accumulated text in current chunk, flush it
                if current_chunk_words:
                    chunk_str = " ".join(current_chunk_words)
                    end_offset = running_char_offset + len(chunk_str)
                    chunks.append(
                        PolicyChunkData(
                            chunk_index=chunk_idx,
                            text=chunk_str,
                            section_heading=current_heading,
                            page_number=initial_page,
                            start_char_offset=running_char_offset,
                            end_char_offset=end_offset,
                        )
                    )
                    chunk_idx += 1
                    running_char_offset = end_offset + 1
                    current_chunk_words = []
                    current_chunk_len = 0

                current_heading = first_line

            para_words = para.split()
            for word in para_words:
                current_chunk_words.append(word)
                current_chunk_len += len(word) + 1

                if current_chunk_len >= self.chunk_size:
                    chunk_str = " ".join(current_chunk_words)
                    end_offset = running_char_offset + len(chunk_str)
                    chunks.append(
                        PolicyChunkData(
                            chunk_index=chunk_idx,
                            text=chunk_str,
                            section_heading=current_heading,
                            page_number=initial_page,
                            start_char_offset=running_char_offset,
                            end_char_offset=end_offset,
                        )
                    )
                    chunk_idx += 1
                    running_char_offset = end_offset + 1

                    # Retain overlap words
                    overlap_words = []
                    overlap_len = 0
                    for w in reversed(current_chunk_words):
                        if overlap_len + len(w) + 1 <= self.chunk_overlap:
                            overlap_words.insert(0, w)
                            overlap_len += len(w) + 1
                        else:
                            break
                    current_chunk_words = overlap_words
                    current_chunk_len = overlap_len

        # Flush final remaining words
        if current_chunk_words:
            chunk_str = " ".join(current_chunk_words)
            end_offset = running_char_offset + len(chunk_str)
            chunks.append(
                PolicyChunkData(
                    chunk_index=chunk_idx,
                    text=chunk_str,
                    section_heading=current_heading,
                    page_number=initial_page,
                    start_char_offset=running_char_offset,
                    end_char_offset=end_offset,
                )
            )

        return chunks
