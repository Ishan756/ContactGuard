from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL, make_url

from app.core.config import Settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger
from app.db.session import get_engine

logger = get_logger("contractguard.workflow.checkpointer")


def _postgres_connection_string(url_string: str) -> str:
    url: URL = make_url(url_string)
    if url.get_backend_name() != "postgresql":
        raise ConfigurationError("LangGraph PostgreSQL checkpoints require a PostgreSQL URL.")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


class CheckpointManager:
    """Owns the LangGraph checkpointer connection for the application lifespan."""

    def __init__(
        self,
        settings: Settings,
        *,
        backend: str | None = None,
        sqlite_path: str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.settings = settings
        self.backend = (backend or settings.workflow_checkpoint_backend or "auto").lower()
        self.sqlite_path = sqlite_path or settings.workflow_checkpoint_sqlite_path
        self.database_url = database_url or settings.workflow_checkpoint_database_url
        self.saver: Any | None = None
        self._context: AbstractAsyncContextManager[Any] | None = None

    def _resolve_backend(self) -> str:
        if self.backend != "auto":
            return self.backend
        if self.database_url:
            return (
                "postgres"
                if make_url(self.database_url).get_backend_name() == "postgresql"
                else "sqlite"
            )
        try:
            dialect = get_engine().url.get_backend_name()
        except Exception:
            dialect = make_url(self.settings.async_database_uri).get_backend_name()
        return "postgres" if dialect == "postgresql" else "sqlite"

    async def start(self) -> Any:
        backend = self._resolve_backend()
        if backend == "memory":
            from langgraph.checkpoint.memory import InMemorySaver

            self.saver = InMemorySaver()
            logger.info("LangGraph checkpointer initialized with in-memory backend.")
            return self.saver

        if backend == "sqlite":
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            path = Path(self.sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._context = AsyncSqliteSaver.from_conn_string(str(path))
            self.saver = await self._context.__aenter__()
            await self.saver.setup()
            logger.info("LangGraph checkpoint schema initialized at %s", path)
            return self.saver

        if backend == "postgres":
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            connection_string = _postgres_connection_string(
                self.database_url or str(get_engine().url)
            )
            self._context = AsyncPostgresSaver.from_conn_string(connection_string)
            self.saver = await self._context.__aenter__()
            await self.saver.setup()
            logger.info("LangGraph PostgreSQL checkpoint schema initialized.")
            return self.saver

        raise ConfigurationError(
            f"Unsupported workflow checkpoint backend '{backend}'. "
            "Use auto, postgres, sqlite, or memory."
        )

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.__aexit__(None, None, None)
        self._context = None
        self.saver = None
        logger.info("LangGraph checkpointer closed.")
