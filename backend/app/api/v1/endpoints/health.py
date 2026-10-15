import asyncio
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, status

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas.health import (
    ComponentHealth,
    HealthStatus,
    LiveHealthResponse,
    ReadyHealthResponse,
)

logger = get_logger("contractguard.health")
router = APIRouter(prefix="/health", tags=["Health"])

# Application start time for uptime calculation
START_TIME = time.time()


async def check_qdrant(settings: Settings) -> ComponentHealth:
    """Check connectivity to Qdrant vector database."""
    start = time.perf_counter()
    url = f"http://{settings.qdrant_host}:{settings.qdrant_port}/readyz"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(url)
            latency = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code == 200:
                return ComponentHealth(
                    status=HealthStatus.HEALTHY,
                    details="Qdrant cluster responsive",
                    latency_ms=latency,
                )
            return ComponentHealth(
                status=HealthStatus.DEGRADED,
                details=f"Qdrant returned HTTP {resp.status_code}",
                latency_ms=latency,
            )
    except Exception as exc:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentHealth(
            status=HealthStatus.DEGRADED,
            details=f"Qdrant unreachable: {type(exc).__name__}",
            latency_ms=latency,
        )


async def check_database(settings: Settings) -> ComponentHealth:
    """Check connectivity to PostgreSQL server port."""
    start = time.perf_counter()
    try:
        # Non-blocking network socket check
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.postgres_server, settings.postgres_port),
            timeout=1.5,
        )
        writer.close()
        await writer.wait_closed()
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentHealth(
            status=HealthStatus.HEALTHY,
            details="PostgreSQL port reachable",
            latency_ms=latency,
        )
    except Exception as exc:
        latency = round((time.perf_counter() - start) * 1000, 2)
        return ComponentHealth(
            status=HealthStatus.DEGRADED,
            details=f"PostgreSQL unreachable: {type(exc).__name__}",
            latency_ms=latency,
        )


@router.get(
    "/live",
    response_model=LiveHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Returns HTTP 200 as long as the FastAPI process is actively serving requests.",
)
async def live() -> LiveHealthResponse:
    """Kubernetes / Docker liveness probe."""
    uptime = round(time.time() - START_TIME, 2)
    return LiveHealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
        uptime_seconds=uptime,
    )


@router.get(
    "/ready",
    response_model=ReadyHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Probe",
    description="Verifies app readiness and reports health state of downstream dependencies.",
)
async def ready(settings: Settings = Depends(get_settings)) -> ReadyHealthResponse:
    """Kubernetes / Docker readiness probe checking dependent subsystems."""
    qdrant_check, db_check = await asyncio.gather(
        check_qdrant(settings),
        check_database(settings),
        return_exceptions=True,
    )

    components: dict[str, ComponentHealth] = {
        "api": ComponentHealth(
            status=HealthStatus.HEALTHY,
            details="FastAPI core processing loop active",
            latency_ms=0.1,
        )
    }

    if isinstance(qdrant_check, ComponentHealth):
        components["vector_db_qdrant"] = qdrant_check
    else:
        components["vector_db_qdrant"] = ComponentHealth(
            status=HealthStatus.DEGRADED,
            details=str(qdrant_check),
        )

    if isinstance(db_check, ComponentHealth):
        components["relational_db_postgres"] = db_check
    else:
        components["relational_db_postgres"] = ComponentHealth(
            status=HealthStatus.DEGRADED,
            details=str(db_check),
        )

    # In development mode, API is ready to serve even if infra containers are starting
    overall_status = HealthStatus.HEALTHY
    if any(c.status == HealthStatus.DEGRADED for c in components.values()):
        overall_status = HealthStatus.DEGRADED

    return ReadyHealthResponse(
        status=overall_status,
        app=settings.app_name,
        version=settings.version,
        environment=settings.app_env,
        timestamp=datetime.now(UTC).isoformat(),
        components=components,
    )
