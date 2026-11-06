import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentTextPiece:
    """A source document chunk mapped into the reconstructed document text."""

    start: int
    end: int
    page_number: int
    section_heading: str | None
    source_chunk_id: str


@dataclass(frozen=True)
class ContractChunk:
    """A bounded extraction window with overlap and source provenance."""

    chunk_id: str
    text: str
    start_offset: int
    end_offset: int
    page_number: int
    section_heading: str | None
    source_chunk_ids: list[str]


class DocumentTextMap:
    """Reconstructed, offset-addressable view of an ingested contract.

    Document chunks are already page-aware and ordered. This class joins them into
    a single text so LLM citations can be located precisely and mapped back to
    page, section, and character offsets.
    """

    def __init__(self, text: str, pieces: list[DocumentTextPiece]) -> None:
        self.text = text
        self.pieces = pieces

    @classmethod
    def from_document_chunks(cls, document_chunks: list[Any]) -> "DocumentTextMap":
        ordered = sorted(document_chunks, key=lambda c: c.chunk_index)
        parts: list[str] = []
        pieces: list[DocumentTextPiece] = []
        cursor = 0

        for chunk in ordered:
            if parts:
                parts.append("\n\n")
                cursor += 2

            start = cursor
            parts.append(chunk.text)
            cursor += len(chunk.text)
            pieces.append(
                DocumentTextPiece(
                    start=start,
                    end=cursor,
                    page_number=chunk.page_number,
                    section_heading=chunk.section_heading,
                    source_chunk_id=chunk.id,
                )
            )

        return cls(text="".join(parts), pieces=pieces)

    def _piece_index_at(self, offset: int) -> int:
        if not self.pieces:
            return -1
        for index, piece in enumerate(self.pieces):
            if offset < piece.end:
                return index
        return len(self.pieces) - 1

    def piece_at(self, offset: int) -> DocumentTextPiece | None:
        index = self._piece_index_at(offset)
        return self.pieces[index] if index >= 0 else None

    def section_at(self, offset: int) -> str | None:
        index = self._piece_index_at(offset)
        for prev in range(index, -1, -1):
            if self.pieces[prev].section_heading:
                return self.pieces[prev].section_heading
        return None

    def source_chunk_ids_between(self, start: int, end: int) -> list[str]:
        ids: list[str] = []
        for piece in self.pieces:
            if piece.end <= start or piece.start >= end:
                continue
            if piece.source_chunk_id not in ids:
                ids.append(piece.source_chunk_id)
        return ids

    def locate(self, needle: str, start: int = 0, end: int | None = None) -> tuple[int, int] | None:
        """Locate a model-supplied quote in the source text.

        Tries an exact match first to preserve verbatim wording, then falls back to
        a whitespace-insensitive regex so formatting differences do not discard an
        otherwise valid citation. The returned slice always comes from the source.
        """
        quote = needle.strip()
        if not quote:
            return None

        search_end = len(self.text) if end is None else min(end, len(self.text))
        search_start = max(0, start)
        exact = self.text.find(quote, search_start, search_end)
        if exact != -1:
            return exact, exact + len(quote)

        tokens = quote.split()
        if not tokens:
            return None
        pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens))
        match = pattern.search(self.text, search_start, search_end)
        if match:
            return match.start(), match.end()
        return None


class ContractChunker:
    """Split long contracts into bounded, overlapping extraction windows."""

    def __init__(self, chunk_size: int = 6000, chunk_overlap: int = 600) -> None:
        self.chunk_size = max(200, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size // 2))

    def build_chunks(self, text_map: DocumentTextMap, document_id: str) -> list[ContractChunk]:
        text = text_map.text
        if not text.strip() or not text_map.pieces:
            return []

        chunks: list[ContractChunk] = []
        length = len(text)
        start = 0
        index = 0

        while start < length:
            end = min(start + self.chunk_size, length)
            if end < length:
                boundary = text.rfind(" ", start + self.chunk_size // 2, end)
                if boundary > start:
                    end = boundary

            raw_window = text[start:end]
            leading_trim = len(raw_window) - len(raw_window.lstrip())
            window_start = start + leading_trim
            window_end = window_start + len(raw_window.strip())
            window_text = text[window_start:window_end]

            if window_text:
                piece = text_map.piece_at(window_start)
                chunks.append(
                    ContractChunk(
                        chunk_id=f"exc:{document_id}:{index}",
                        text=window_text,
                        start_offset=window_start,
                        end_offset=window_end,
                        page_number=piece.page_number if piece else 1,
                        section_heading=text_map.section_at(window_start),
                        source_chunk_ids=text_map.source_chunk_ids_between(
                            window_start, window_end
                        ),
                    )
                )
                index += 1

            if end >= length:
                break

            next_start = max(end - self.chunk_overlap, start + 1)
            whitespace = text.find(" ", next_start, end)
            if whitespace != -1 and whitespace + 1 < end:
                next_start = whitespace + 1
            start = next_start if next_start > start else end

        return chunks
