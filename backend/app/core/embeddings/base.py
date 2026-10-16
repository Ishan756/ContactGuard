from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract interface for dense vector embedding generators."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Expected output dimension of generated vectors."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the underlying embedding model."""
        pass

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Generate a single vector embedding for query or text passage."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of text strings in batch."""
        pass
