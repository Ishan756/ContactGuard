from datetime import UTC, datetime

from pydantic import BaseModel, Field


class APIResponse[DataT](BaseModel):
    """Standard success API envelope wrapper."""

    success: bool = Field(default=True, description="Indicates call success")
    data: DataT = Field(..., description="Response payload")
    request_id: str | None = Field(default=None, description="Tracing request ID")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp",
    )


class MessageResponse(BaseModel):
    """Simple confirmation or message payload."""

    message: str = Field(..., description="Informational message")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC timestamp",
    )
