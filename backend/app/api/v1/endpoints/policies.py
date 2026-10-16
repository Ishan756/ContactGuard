from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.factory import get_embedding_provider
from app.db.models import Policy
from app.db.session import get_db
from app.schemas.policy import (
    PolicyCreateRequest,
    PolicyListResponse,
    PolicyResponse,
    PolicySearchRequest,
    PolicySearchResponse,
    PolicyUpdateRequest,
)
from app.services.policy.service import PolicyService
from app.services.vector.qdrant_service import QdrantVectorService

router = APIRouter(prefix="/policies", tags=["Policies"])


def get_policy_service(
    settings: Settings = Depends(get_settings),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
) -> PolicyService:
    vector_service = QdrantVectorService(settings)
    return PolicyService(
        vector_service=vector_service,
        embedding_provider=embedding_provider,
        settings=settings,
    )


def map_policy_response(p: Policy) -> PolicyResponse:
    return PolicyResponse(
        id=p.id,
        name=p.name,
        version=p.version,
        category=p.category,
        description=p.description,
        status=p.status,
        source_document_id=p.source_document_id,
        total_chunks=p.total_chunks,
        created_at=p.created_at.isoformat() if isinstance(p.created_at, datetime) else str(p.created_at),
        updated_at=p.updated_at.isoformat() if isinstance(p.updated_at, datetime) else str(p.updated_at),
    )


@router.post(
    "",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a company policy with textual rules",
    description="Creates a policy and vector-indexes its rules for contract clause auditing.",
)
async def create_policy(
    request: PolicyCreateRequest,
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    policy = await policy_service.create_policy(request, db)
    return map_policy_response(policy)


@router.post(
    "/upload",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and vectorize a company policy document (PDF/DOCX)",
    description="Ingests a PDF or DOCX policy document, splits by paragraphs and headings, and indexes into Qdrant.",
)
async def upload_policy_document(
    name: str = Form(..., description="Policy name"),
    version: str = Form(default="1.0.0", description="Policy version"),
    category: str | None = Form(default=None, description="Domain category"),
    description: str | None = Form(default=None, description="Description"),
    file: UploadFile = File(..., description="PDF or DOCX policy document"),
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    policy = await policy_service.upload_policy_document(
        name=name,
        version=version,
        category=category,
        description=description,
        file=file,
        db=db,
    )
    return map_policy_response(policy)


@router.get(
    "",
    response_model=PolicyListResponse,
    summary="List all company policies",
)
async def list_policies(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyListResponse:
    policies, total = await policy_service.list_policies(
        limit=limit,
        offset=offset,
        category=category,
        status=status,
        db=db,
    )
    return PolicyListResponse(
        policies=[map_policy_response(p) for p in policies],
        total=total,
    )


@router.get(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Get policy metadata and indexing status",
)
async def get_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    policy = await policy_service.get_policy(policy_id, db)
    return map_policy_response(policy)


@router.put(
    "/{policy_id}",
    response_model=PolicyResponse,
    summary="Update policy metadata or rules content",
    description="Updates policy and automatically re-indexes vector representations if content is modified.",
)
async def update_policy(
    policy_id: str,
    request: PolicyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicyResponse:
    policy = await policy_service.update_policy(policy_id, request, db)
    return map_policy_response(policy)


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a policy and purge all vectors",
)
async def delete_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db),
    policy_service: PolicyService = Depends(get_policy_service),
) -> None:
    await policy_service.delete_policy(policy_id, db)


@router.post(
    "/search",
    response_model=PolicySearchResponse,
    summary="Semantic retrieval of relevant company policy passages",
    description="Embeds input contract clause and retrieves nearest policy rules with cosine similarity scores.",
)
async def search_policies(
    search_req: PolicySearchRequest,
    policy_service: PolicyService = Depends(get_policy_service),
) -> PolicySearchResponse:
    return await policy_service.search_policies(search_req)
