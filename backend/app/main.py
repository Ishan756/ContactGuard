from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware
from app.schemas.health import RootHealthResponse

settings = get_settings()
setup_logging(
    log_level=settings.app_log_level,
    structured_json=settings.is_production,
)
logger = get_logger("contractguard.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle management for startup and graceful shutdown."""
    logger.info(
        "Starting %s v%s in %s mode",
        settings.app_name,
        settings.version,
        settings.app_env,
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_application() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=f"{settings.app_name} API",
        description="Production-grade AI-powered multi-agent contract risk auditing platform API.",
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # 1. Custom Request Context & ID Middleware (executed outer)
    app.add_middleware(RequestContextMiddleware)

    # 2. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
    )

    # 3. Centralized Exception Handlers
    register_exception_handlers(app)

    # 4. Root Health Check Endpoint
    @app.get(
        "/health",
        response_model=RootHealthResponse,
        status_code=status.HTTP_200_OK,
        tags=["Health"],
        summary="Service Root Health Probe",
        description="Quick service ping returning deployment metadata and documentation link.",
    )
    async def root_health() -> RootHealthResponse:
        return RootHealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.version,
            docs_url="/docs",
            timestamp=datetime.now(UTC).isoformat(),
        )

    # 5. Mount API v1 Routers
    app.include_router(api_v1_router)

    return app


app = create_application()
