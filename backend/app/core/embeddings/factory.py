from functools import lru_cache
from app.core.config import get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.gemini import GeminiEmbeddingProvider
from app.core.embeddings.mock import DeterministicEmbeddingProvider


@lru_cache()
def get_embedding_provider() -> EmbeddingProvider:
    """Factory creating the configured embedding provider."""
    settings = get_settings()
    provider_type = settings.embedding_provider.lower().strip()

    if provider_type in ("mock", "deterministic", "test"):
        return DeterministicEmbeddingProvider(
            dimension=settings.embedding_dimension,
            model_name=settings.embedding_model,
        )

    # If Gemini API key is missing or dummy placeholder, fallback gracefully to deterministic provider
    if not settings.gemini_api_key or settings.gemini_api_key in ("your-gemini-api-key-here", "test-gemini-key"):
        return DeterministicEmbeddingProvider(
            dimension=settings.embedding_dimension,
            model_name=settings.embedding_model,
        )

    return GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )
