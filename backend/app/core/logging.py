import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Context variable for tracing request IDs across async tasks and logs
request_id_ctx_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_current_request_id() -> str | None:
    """Retrieve the current request ID from context."""
    return request_id_ctx_var.get()


class JSONStructuredFormatter(logging.Formatter):
    """Custom logging formatter outputting clean, machine-readable structured JSON."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = get_current_request_id()
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": req_id or getattr(record, "request_id", None),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include custom extra fields if provided
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            payload.update(record.extra_data)

        return json.dumps(payload, default=str)


class TextStructuredFormatter(logging.Formatter):
    """Human-friendly structured formatter for local console readability."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = get_current_request_id() or getattr(record, "request_id", "--------")
        req_id_short = req_id[:8] if req_id else "--------"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()

        base = f"[{timestamp}] [{record.levelname:<7}] [req:{req_id_short}] {record.name}: {msg}"
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


def setup_logging(log_level: str = "INFO", structured_json: bool = False) -> None:
    """Configure root logger with structured formatting."""
    root_logger = logging.getLogger()
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    if structured_json:
        stream_handler.setFormatter(JSONStructuredFormatter())
    else:
        stream_handler.setFormatter(TextStructuredFormatter())

    root_logger.addHandler(stream_handler)

    # Adjust external noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Convenience helper to obtain a named logger."""
    return logging.getLogger(name)
