import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger, request_id_ctx_var

logger = get_logger("contractguard.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware for request-id tracing, contextual logging, and latency instrumentation."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if caller provided a request id or generate a new UUID4
        req_id = request.headers.get("X-Request-ID")
        if not req_id or not req_id.strip():
            req_id = str(uuid.uuid4())

        # Bind to context variable for thread/task-local access
        token = request_id_ctx_var.set(req_id)
        request.state.request_id = req_id

        start_time = time.perf_counter()
        logger.debug(
            "--> %s %s [req_id=%s]",
            request.method,
            request.url.path,
            req_id,
        )

        try:
            response: Response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = req_id
            response.headers["X-Response-Time-Ms"] = str(duration_ms)

            logger.info(
                "<-- %s %s completed %s in %sms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "<-- %s %s failed after %sms: %s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            raise exc

        finally:
            request_id_ctx_var.reset(token)
