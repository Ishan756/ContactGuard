import uuid
from fastapi import UploadFile
from qdrant_client import models
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.factory import get_embedding_provider
from app.core.errors import AppException, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.models import DocumentChunk, Policy, PolicyChunk, PolicyStatus
from app.schemas.policy import (
    PolicyCreateRequest,
    PolicySearchRequest,
    PolicySearchResultItem,
    PolicySearchResponse,
    PolicyUpdateRequest,
)
from app.services.ingestion.service import DocumentIngestionService
from app.services.policy.chunker import PolicyChunkData, PolicyChunker
from app.services.vector.qdrant_service import QdrantVectorService
from app.storage.factory import get_storage_backend

logger = get_logger("contractguard.policy.service")


class PolicyService:
    """Manages policy lifecycle, document ingestion, vectorization, and semantic retrieval."""

    def __init__(
        self,
        vector_service: QdrantVectorService | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.vector_service = vector_service or QdrantVectorService(self.settings)
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.chunker = PolicyChunker(
            chunk_size=self.settings.policy_chunk_size,
            chunk_overlap=self.settings.policy_chunk_overlap,
        )
        self.collection_name = self.settings.qdrant_policy_collection

    async def _ensure_collection_ready(self) -> None:
        """Validate or create the Qdrant collection with expected embedding dimensions."""
        await self.vector_service.ensure_collection(
            collection_name=self.collection_name,
            dimension=self.embedding_provider.dimension,
        )

    async def _index_chunks_in_qdrant(
        self,
        policy: Policy,
        chunks_data: list[PolicyChunkData],
        db: AsyncSession,
    ) -> None:
        """Embed chunks, store vectors in Qdrant, and persist chunks in database."""
        if not chunks_data:
            return

        # 1. Clean existing vectors if updating
        await self.vector_service.delete_by_policy_id(
            collection_name=self.collection_name,
            policy_id=policy.id,
        )

        # 2. Generate embeddings
        texts = [c.text for c in chunks_data]
        try:
            vectors = await self.embedding_provider.embed_batch(texts)
        except Exception as exc:
            logger.error("Failed to generate vector embeddings: %s", exc)
            raise AppException(f"Embedding generation failed: {exc}", code="EMBEDDING_FAILED")

        points: list[models.PointStruct] = []
        chunk_models: list[PolicyChunk] = []

        for chunk_item, vector in zip(chunks_data, vectors, strict=True):
            chunk_id = str(uuid.uuid4())
            vector_id = str(uuid.uuid4())
            source_id = f"pol:{policy.id}:p{chunk_item.page_number}:c{chunk_item.chunk_index}"

            payload = {
                "chunk_id": chunk_id,
                "policy_id": policy.id,
                "policy_name": policy.name,
                "policy_version": policy.version,
                "category": policy.category,
                "section_heading": chunk_item.section_heading,
                "page_number": chunk_item.page_number,
                "start_char_offset": chunk_item.start_char_offset,
                "end_char_offset": chunk_item.end_char_offset,
                "text": chunk_item.text,
                "source_identifier": source_id,
            }

            points.append(
                models.PointStruct(
                    id=vector_id,
                    vector=vector,
                    payload=payload,
                )
            )

            chunk_models.append(
                PolicyChunk(
                    id=chunk_id,
                    policy_id=policy.id,
                    chunk_index=chunk_item.chunk_index,
                    section_heading=chunk_item.section_heading,
                    page_number=chunk_item.page_number,
                    start_char_offset=chunk_item.start_char_offset,
                    end_char_offset=chunk_item.end_char_offset,
                    text=chunk_item.text,
                    source_identifier=source_id,
                    vector_id=vector_id,
                )
            )

        # 3. Store points in Qdrant
        await self.vector_service.upsert_points(
            collection_name=self.collection_name,
            points=points,
        )

        # 4. Save chunk records in DB
        for cm in chunk_models:
            db.add(cm)

        policy.total_chunks = len(chunk_models)
        await db.commit()
        await db.refresh(policy)

    async def create_policy(
        self,
        request: PolicyCreateRequest,
        db: AsyncSession,
    ) -> Policy:
        # Prevent exact duplicate policy name and version
        stmt = select(Policy).where(Policy.name == request.name, Policy.version == request.version)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise ValidationError(
                f"Policy '{request.name}' with version '{request.version}' already exists.",
            )

        await self._ensure_collection_ready()

        policy = Policy(
            id=str(uuid.uuid4()),
            name=request.name,
            version=request.version,
            category=request.category,
            description=request.description,
            status=PolicyStatus.ACTIVE,
            total_chunks=0,
        )
        db.add(policy)
        await db.flush()

        if request.text_content and request.text_content.strip():
            chunks_data = self.chunker.chunk_text(request.text_content)
            await self._index_chunks_in_qdrant(policy, chunks_data, db)
        else:
            await db.commit()
            await db.refresh(policy)

        return policy

    async def upload_policy_document(
        self,
        name: str,
        version: str,
        category: str | None,
        description: str | None,
        file: UploadFile,
        db: AsyncSession,
    ) -> Policy:
        """Upload a PDF or DOCX file as a policy, reusing secure ingestion and extracting text."""
        stmt = select(Policy).where(Policy.name == name, Policy.version == version)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise ValidationError(
                f"Policy '{name}' with version '{version}' already exists.",
            )

        await self._ensure_collection_ready()

        # Ingest file using DocumentIngestionService
        storage = get_storage_backend()
        ingestion = DocumentIngestionService(storage=storage, settings=self.settings)
        doc = await ingestion.ingest_document(upload_file=file, db=db)

        if doc.status == "failed":
            raise AppException(f"Failed to parse policy document: {doc.error_message}", code="INGESTION_FAILED")

        policy = Policy(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
            category=category,
            description=description,
            status=PolicyStatus.ACTIVE,
            source_document_id=doc.id,
            total_chunks=0,
        )
        db.add(policy)
        await db.flush()

        # Re-chunk from document chunks to ensure consistent policy chunk size & overlap
        chunks_stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc.id).order_by(DocumentChunk.chunk_index)
        doc_chunks = (await db.execute(chunks_stmt)).scalars().all()

        chunks_data: list[PolicyChunkData] = []
        chunk_idx = 0
        for dc in doc_chunks:
            sub_chunks = self.chunker.chunk_text(
                full_text=dc.text,
                initial_page=dc.page_number,
                initial_heading=dc.section_heading,
            )
            for sc in sub_chunks:
                sc.chunk_index = chunk_idx
                chunks_data.append(sc)
                chunk_idx += 1

        await self._index_chunks_in_qdrant(policy, chunks_data, db)
        return policy

    async def update_policy(
        self,
        policy_id: str,
        request: PolicyUpdateRequest,
        db: AsyncSession,
    ) -> Policy:
        policy = await self.get_policy(policy_id, db)

        if request.name is not None:
            policy.name = request.name
        if request.version is not None:
            policy.version = request.version
        if request.category is not None:
            policy.category = request.category
        if request.description is not None:
            policy.description = request.description
        if request.status is not None:
            policy.status = request.status

        # If updated text provided, re-index and delete stale vectors
        if request.text_content is not None:
            await self._ensure_collection_ready()
            # Remove old chunk rows from DB
            await db.execute(delete(PolicyChunk).where(PolicyChunk.policy_id == policy.id))
            chunks_data = self.chunker.chunk_text(request.text_content)
            await self._index_chunks_in_qdrant(policy, chunks_data, db)
        else:
            await db.commit()
            await db.refresh(policy)

        return policy

    async def delete_policy(
        self,
        policy_id: str,
        db: AsyncSession,
    ) -> None:
        policy = await self.get_policy(policy_id, db)
        # 1. Clean Qdrant vectors to prevent stale contamination
        await self.vector_service.delete_by_policy_id(
            collection_name=self.collection_name,
            policy_id=policy.id,
        )
        # 2. Delete database record (cascades to chunks)
        await db.delete(policy)
        await db.commit()
        logger.info("Deleted policy %s and associated Qdrant vectors", policy_id)

    async def get_policy(
        self,
        policy_id: str,
        db: AsyncSession,
    ) -> Policy:
        stmt = select(Policy).where(Policy.id == policy_id)
        result = await db.execute(stmt)
        policy = result.scalar_one_or_none()
        if not policy:
            raise NotFoundError(f"Policy with ID '{policy_id}' not found.")
        return policy

    async def list_policies(
        self,
        limit: int,
        offset: int,
        db: AsyncSession,
        category: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Policy], int]:
        stmt = select(Policy)
        if category:
            stmt = stmt.where(Policy.category == category)
        if status:
            stmt = stmt.where(Policy.status == status)

        # Count total
        count_res = await db.execute(stmt)
        total = len(count_res.scalars().all())

        stmt = stmt.order_by(Policy.created_at.desc()).offset(offset).limit(limit)
        res = await db.execute(stmt)
        policies = list(res.scalars().all())
        return policies, total

    async def search_policies(
        self,
        search_req: PolicySearchRequest,
    ) -> PolicySearchResponse:
        query = search_req.query.strip()
        if not query:
            raise ValidationError("Search query cannot be empty.")

        await self._ensure_collection_ready()

        # 1. Generate query vector
        try:
            query_vector = await self.embedding_provider.embed_text(query)
        except Exception as exc:
            logger.error("Failed to embed search query: %s", exc)
            raise AppException(f"Failed to generate query embedding: {exc}", code="EMBEDDING_FAILED")

        limit = search_req.limit or self.settings.policy_retrieval_limit

        # 2. Execute semantic retrieval
        matches = await self.vector_service.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            policy_id=search_req.policy_id,
            category=search_req.category,
            min_score=search_req.min_similarity,
        )

        items: list[PolicySearchResultItem] = []
        for m in matches:
            p = m.payload
            items.append(
                PolicySearchResultItem(
                    chunk_id=p.get("chunk_id", m.id),
                    source_identifier=p.get("source_identifier", f"chunk:{m.id}"),
                    policy_id=p.get("policy_id", ""),
                    policy_name=p.get("policy_name", "Unknown Policy"),
                    policy_version=p.get("policy_version", "1.0.0"),
                    category=p.get("category"),
                    section_heading=p.get("section_heading"),
                    page_number=p.get("page_number", 1),
                    start_char_offset=p.get("start_char_offset", 0),
                    end_char_offset=p.get("end_char_offset", 0),
                    text=p.get("text", ""),
                    similarity_score=round(m.score, 4),
                )
            )

        return PolicySearchResponse(
            query=query,
            total_results=len(items),
            model_used=self.embedding_provider.model_name,
            dimension=self.embedding_provider.dimension,
            results=items,
        )
