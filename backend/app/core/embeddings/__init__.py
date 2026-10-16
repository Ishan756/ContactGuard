"""Embedding providers and vector factory."""

from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.factory import get_embedding_provider

__all__ = ["EmbeddingProvider", "get_embedding_provider"]
