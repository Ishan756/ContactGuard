from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_current_request_id, get_logger

logger = get_logger("contractguard.errors")


class ErrorDetail(BaseModel):
    """Normalized error detail representation."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Any | None = Field(default=None, description="Optional diagnostic details")


class ErrorResponse(BaseModel):
    """Consistent API error response contract."""

    error: ErrorDetail = Field(..., description="Error detail object")
    request_id: str | None = Field(default=None, description="Tracing request ID")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")


class AppException(Exception):
    """Base class for all business/application exceptions."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class UnauthorizedError(AppException):
    def __init__(
        self, message: str = "Authentication required", details: Any | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Access denied", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "Resource conflict", details: Any | None = None) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ServiceUnavailableError(AppException):
    def __init__(
        self, message: str = "Downstream service unavailable", details: Any | None = None
    ) -> None:
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
        )


def build_error_payload(
    code: str,
    message: str,
    details: Any | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Helper to construct standard error JSON payload."""
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "request_id": request_id or get_current_request_id(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler for all domain and operational AppExceptions."""
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.warning(
        f"Application error: {exc.code} - {exc.message} (HTTP {exc.status_code})",
        extra={"extra_data": {"status_code": exc.status_code, "error_code": exc.code}},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(
            code=exc.code,
            message=exc.message,
            details=exc.details,
            request_id=req_id,
        ),
        headers={"X-Request-ID": req_id} if req_id else {},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handler for FastAPI / Pydantic schema validation errors."""
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.warning("Request validation failed for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_error_payload(
            code="VALIDATION_ERROR",
            message="Request body or query parameters failed validation",
            details=exc.errors(),
            request_id=req_id,
        ),
        headers={"X-Request-ID": req_id} if req_id else {},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled 500 server errors."""
    req_id = getattr(request.state, "request_id", get_current_request_id())
    logger.exception(
        "Unhandled server exception processing %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=build_error_payload(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please contact support with the request ID.",
            details=None,
            request_id=req_id,
        ),
        headers={"X-Request-ID": req_id} if req_id else {},
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handler for standard Starlette/FastAPI HTTPExceptions (e.g., 404 Not Found, 405)."""
    req_id = getattr(request.state, "request_id", get_current_request_id())
    code_map = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    logger.info(
        "HTTP %s for %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(
            code=code,
            message=str(exc.detail),
            details=None,
            request_id=req_id,
        ),
        headers={"X-Request-ID": req_id} if req_id else {},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all centralized exception handlers to the FastAPI app instance."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
