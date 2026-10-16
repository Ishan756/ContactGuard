import hashlib
import math
from app.core.embeddings.base import EmbeddingProvider


class DeterministicEmbeddingProvider(EmbeddingProvider):
    """Deterministic, zero-cost embedding provider for hermetic testing and offline development.
    
    Uses SHA-256 and periodic projections to create normalized, dimension-compliant float vectors.
    Semantic similarity between identical or overlapping tokens yields consistent cosine distances.
    """

    def __init__(self, dimension: int = 768, model_name: str = "deterministic-embedding") -> None:
        self._dimension = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _generate_vector(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dimension

        vector = [0.0] * self._dimension
        words = text.lower().split()
        
        # Token hash projection
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            for idx in range(min(len(w) * 16, self._dimension)):
                pos = (h + idx * 31) % self._dimension
                weight = 1.0 + (h % 7) * 0.1
                vector[pos] += weight

        # Global document signature
        full_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        for i in range(self._dimension):
            char_val = int(full_hash[(i * 2) % len(full_hash)], 16)
            vector[i] += (char_val - 7.5) * 0.05

        # L2 Normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0.0:
            vector = [v / norm for v in vector]
        return vector

    async def embed_text(self, text: str) -> list[float]:
        return self._generate_vector(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._generate_vector(t) for t in texts]
