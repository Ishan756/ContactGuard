from dataclasses import dataclass
from typing import Any
from qdrant_client import AsyncQdrantClient, models
from app.core.config import Settings, get_settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger("contractguard.vector_store")


@dataclass
class ScoredVectorMatch:
    id: str
    score: float
    payload: dict[str, Any]


class QdrantVectorService:
    """Manages Qdrant vector collections, vector upserts, deletes, and semantic searches."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: AsyncQdrantClient | None = None

    def get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port,
                api_key=self.settings.qdrant_api_key,
                timeout=3.0,
            )
        return self._client

    async def ensure_collection(self, collection_name: str, dimension: int) -> None:
        """Create collection if absent, or validate that existing collection vector dimension matches."""
        client = self.get_client()
        try:
            collections = await client.get_collections()
            existing_names = [c.name for c in collections.collections]

            if collection_name not in existing_names:
                logger.info(
                    "Creating Qdrant collection '%s' with dimension %d",
                    collection_name,
                    dimension,
                )
                await client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    ),
                )
            else:
                # Validate dimensional compatibility
                info = await client.get_collection(collection_name=collection_name)
                # Handle vector config check
                vectors_config = info.config.params.vectors
                current_dim = getattr(vectors_config, "size", None)
                if current_dim and current_dim != dimension:
                    logger.error(
                        "Collection '%s' has dimension %d, but configured embedding dimension is %d! "
                        "Rejecting operation to prevent dimension contamination.",
                        collection_name,
                        current_dim,
                        dimension,
                    )
                    raise ServiceUnavailableError(
                        f"Vector collection dimension mismatch: expected {dimension}, found {current_dim}."
                    )
        except Exception as exc:
            logger.warning("Qdrant ensure_collection check failed (%s)", exc)
            raise ServiceUnavailableError(f"Qdrant service unavailable or collection error: {exc}")

    async def upsert_points(
        self,
        collection_name: str,
        points: list[models.PointStruct],
    ) -> None:
        """Upsert points into specified Qdrant collection."""
        if not points:
            return

        client = self.get_client()
        try:
            await client.upsert(
                collection_name=collection_name,
                points=points,
            )
        except Exception as exc:
            logger.error("Failed to upsert points into Qdrant collection %s: %s", collection_name, exc)
            raise ServiceUnavailableError(f"Qdrant vector upsert failed: {exc}")

    async def delete_by_policy_id(self, collection_name: str, policy_id: str) -> None:
        """Purge all vectors corresponding to a policy ID to avoid stale vector contamination."""
        client = self.get_client()
        try:
            # Check if collection exists
            collections = await client.get_collections()
            if collection_name not in [c.name for c in collections.collections]:
                return

            await client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="policy_id",
                                match=models.MatchValue(value=policy_id),
                            )
                        ]
                    )
                ),
            )
            logger.info("Purged vector points for policy_id=%s from %s", policy_id, collection_name)
        except Exception as exc:
            logger.warning("Failed to delete vectors for policy_id=%s: %s", policy_id, exc)

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        policy_id: str | None = None,
        category: str | None = None,
        min_score: float = 0.0,
    ) -> list[ScoredVectorMatch]:
        """Perform cosine similarity vector search with optional metadata filters."""
        client = self.get_client()
        try:
            must_conditions = []
            if policy_id:
                must_conditions.append(
                    models.FieldCondition(
                        key="policy_id",
                        match=models.MatchValue(value=policy_id),
                    )
                )
            if category:
                must_conditions.append(
                    models.FieldCondition(
                        key="category",
                        match=models.MatchValue(value=category),
                    )
                )

            query_filter = models.Filter(must=must_conditions) if must_conditions else None

            # Execute search
            results = await client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=min_score if min_score > 0.0 else None,
            )

            matches = []
            for hit in results:
                matches.append(
                    ScoredVectorMatch(
                        id=str(hit.id),
                        score=float(hit.score),
                        payload=hit.payload or {},
                    )
                )
            return matches
        except Exception as exc:
            logger.error("Vector search failed on collection %s: %s", collection_name, exc)
            raise ServiceUnavailableError(f"Vector search failed: {exc}")
