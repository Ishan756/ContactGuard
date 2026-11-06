from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.errors import ConfigurationError
from app.core.llm.base import LLMProvider
from app.core.llm.gemini import GeminiLLMProvider
from app.core.llm.mock import MockLLMProvider


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Build the configured LLM provider.

    Missing Gemini credentials produce an explicit configuration error. Tests and
    offline development must opt in to the mock provider via LLM_PROVIDER=mock.
    """
    provider = settings.llm_provider.strip().lower()

    if provider in ("mock", "test", "deterministic"):
        return MockLLMProvider(model_name=settings.resolved_llm_model)

    if provider != "gemini":
        raise ConfigurationError(
            f"Unsupported LLM provider '{settings.llm_provider}'. Use 'gemini' or 'mock'.",
            details={"provider": settings.llm_provider},
        )

    return GeminiLLMProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.resolved_llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_output_tokens=settings.llm_max_output_tokens,
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Cached FastAPI dependency for the configured LLM provider."""
    return create_llm_provider(get_settings())
