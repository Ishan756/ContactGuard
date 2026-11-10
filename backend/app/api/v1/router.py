from fastapi import APIRouter

from app.api.v1.endpoints import (
    clauses,
    comparisons,
    documents,
    evaluation,
    health,
    policies,
    risk,
    workflows,
)

api_v1_router = APIRouter(prefix="/api/v1")

# Mount endpoints
api_v1_router.include_router(health.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(clauses.router)
api_v1_router.include_router(policies.router)
api_v1_router.include_router(risk.router)
api_v1_router.include_router(workflows.router)
api_v1_router.include_router(comparisons.router)
api_v1_router.include_router(evaluation.router)
