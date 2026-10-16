import asyncio
from google import genai
from app.core.config import get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.errors import AppException, ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger("contractguard.embeddings.gemini")


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini embedding provider using official google-genai client."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "text-embedding-004",
        dimension: int = 768,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model_name = model_name
        self._dimension = dimension
        self._client: genai.Client | None = None

        if self._api_key and self._api_key != "your-gemini-api-key-here" and self._api_key != "test-gemini-key":
            try:
                self._client = genai.Client(api_key=self._api_key)
            except Exception as exc:
                logger.warning("Failed to initialize Google GenAI Client: %s", exc)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_batch([text])
        if not vectors:
            raise AppException("No embedding vector returned by Gemini API", code="EMBEDDING_EMPTY")
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._client:
            raise ServiceUnavailableError(
                "Gemini API key is not configured or client initialization failed. "
                "Set GEMINI_API_KEY in your environment or use EMBEDDING_PROVIDER=mock for offline development."
            )

        def _call_gemini() -> list[list[float]]:
            try:
                response = self._client.models.embed_content(
                    model=self._model_name,
                    contents=texts,
                )
                embeddings = []
                for emb in response.embeddings:
                    values = emb.values
                    # Validate vector dimensions
                    if len(values) != self._dimension:
                        logger.warning(
                            "Gemini model %s returned %d dims (configured: %d)",
                            self._model_name,
                            len(values),
                            self._dimension,
                        )
                    embeddings.append(values)
                return embeddings
            except Exception as exc:
                logger.error("Gemini embed_content call failed: %s", exc)
                raise ServiceUnavailableError(f"Gemini embedding API call failed: {exc}")

        return await asyncio.to_thread(_call_gemini)
