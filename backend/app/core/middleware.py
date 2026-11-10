import asyncio
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.logging import get_logger, request_id_ctx_var
from app.core.metrics import metrics

logger = get_logger("contractguard.access")

_RATE_LIMIT_EXEMPT_PATHS = {
    "/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class _SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._requests_since_cleanup = 0

    def check(self, client_key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[client_key]
            while events and events[0] <= cutoff:
                events.popleft()
            allowed = len(events) < limit
            if allowed:
                events.append(now)
            remaining = max(limit - len(events), 0)
            retry_after = (
                max(int(window_seconds - (now - events[0])) + 1, 1) if events else 1
            )
            self._requests_since_cleanup += 1
            if self._requests_since_cleanup >= 1000:
                self._cleanup(cutoff)
                self._requests_since_cleanup = 0
            return allowed, remaining, retry_after

    def _cleanup(self, cutoff: float) -> None:
        stale = [key for key, events in self._events.items() if not events or events[-1] <= cutoff]
        for key in stale:
            self._events.pop(key, None)


_rate_limiter = _SlidingWindowRateLimiter()


def _client_key(request: Request, trust_proxy_headers: bool) -> str:
    if trust_proxy_headers:
        real_ip = (request.headers.get("X-Real-IP") or "").strip()
        if real_ip:
            return real_ip[:128]
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Request tracing, access logging, rate limiting, timeout, and metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        supplied_req_id = request.headers.get("X-Request-ID") or ""
        req_id = "".join(
            char for char in supplied_req_id if 32 <= ord(char) < 127
        ).strip()[:128]
        if not req_id:
            req_id = str(uuid.uuid4())

        token = request_id_ctx_var.set(req_id)
        request.state.request_id = req_id
        start_time = time.perf_counter()

        if settings.rate_limit_enabled and not self._is_rate_limit_exempt(request.url.path):
            client_key = _client_key(request, settings.trust_proxy_headers)
            allowed, remaining, retry_after = _rate_limiter.check(
                client_key,
                settings.rate_limit_requests_per_minute,
                settings.rate_limit_window_seconds,
            )
            if not allowed:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.warning(
                    "Rate limit exceeded for %s on %s %s",
                    client_key,
                    request.method,
                    request.url.path,
                )
                metrics.record_request(
                    request.method,
                    "rate_limit",
                    429,
                    duration_ms,
                )
                request_id_ctx_var.reset(token)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limit_exceeded",
                            "message": "Too many requests. Please retry later.",
                            "request_id": req_id,
                        }
                    },
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(
                            settings.rate_limit_requests_per_minute
                        ),
                        "X-RateLimit-Remaining": "0",
                        "X-Request-ID": req_id,
                    },
                )

        try:
            logger.debug("--> %s %s", request.method, request.url.path)
            response: Response = await asyncio.wait_for(
                call_next(request),
                timeout=settings.request_timeout_seconds,
            )
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            route = getattr(request.scope.get("route"), "path", request.url.path)
            metrics.record_request(request.method, route, response.status_code, duration_ms)
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Response-Time-Ms"] = str(duration_ms)
            logger.info(
                "Request completed method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "extra_data": {
                        "event": "http_request_completed",
                        "method": request.method,
                        "path": request.url.path,
                        "route": route,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    }
                },
            )
            return response

        except TimeoutError:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            route = getattr(request.scope.get("route"), "path", "unmatched")
            metrics.record_request(request.method, route, 504, duration_ms)
            logger.error(
                "Request timed out method=%s path=%s timeout_seconds=%s",
                request.method,
                request.url.path,
                settings.request_timeout_seconds,
                extra={
                    "extra_data": {
                        "event": "http_request_timeout",
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": duration_ms,
                    }
                },
            )
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "request_timeout",
                        "message": "Request exceeded the configured processing timeout.",
                        "request_id": req_id,
                    }
                },
                headers={"X-Request-ID": req_id},
            )

        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            route = getattr(request.scope.get("route"), "path", "unmatched")
            metrics.record_request(request.method, route, 500, duration_ms)
            logger.exception(
                "Request failed method=%s path=%s duration_ms=%s error=%s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
            )
            raise

        finally:
            request_id_ctx_var.reset(token)

    @staticmethod
    def _is_rate_limit_exempt(path: str) -> bool:
        return path in _RATE_LIMIT_EXEMPT_PATHS


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach defensive response headers; HSTS is limited to production."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        settings = get_settings()
        if not settings.security_headers_enabled:
            return response

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if settings.is_production and settings.hsts_max_age_seconds > 0:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains",
            )
        return response
