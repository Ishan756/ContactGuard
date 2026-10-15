from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    status: HealthStatus = Field(..., description="Component health state")
    details: str | None = Field(default=None, description="Diagnostic message or version info")
    latency_ms: float | None = Field(default=None, description="Roundtrip check latency in ms")


class RootHealthResponse(BaseModel):
    status: str = Field(default="ok", description="High-level system status")
    service: str = Field(..., description="Service identifier")
    version: str = Field(..., description="Current deployment version")
    docs_url: str = Field(..., description="Interactive documentation endpoint")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")


class LiveHealthResponse(BaseModel):
    status: str = Field(default="ok", description="Liveness probe status")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")


class ReadyHealthResponse(BaseModel):
    status: HealthStatus = Field(..., description="Overall readiness status")
    app: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Runtime environment")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    components: dict[str, ComponentHealth] = Field(
        default_factory=dict,
        description="Health states of downstream dependencies",
    )
