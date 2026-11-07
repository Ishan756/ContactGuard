from fastapi import APIRouter

from app.api.v1.endpoints import clauses, documents, health, policies, risk

api_v1_router = APIRouter(prefix="/api/v1")

# Mount endpoints
api_v1_router.include_router(health.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(clauses.router)
api_v1_router.include_router(policies.router)
api_v1_router.include_router(risk.router)
