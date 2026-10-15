from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Base

logger = get_logger("contractguard.db")
settings = get_settings()

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = settings.database_url
        if not db_url:
            # Check if sqlite file directory exists
            Path("data").mkdir(parents=True, exist_ok=True)
            db_url = "sqlite+aiosqlite:///data/contractguard.db"

        logger.info("Initializing database engine with URL schema: %s", db_url.split("://")[0])
        _engine = create_async_engine(
            db_url,
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        engine = get_engine()
        _session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_maker


async def init_db() -> None:
    """Initialize database tables."""
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema verified and initialized.")
    except Exception as exc:
        logger.warning(
            "Primary database connection failed (%s). Falling back to local SQLite async database.",
            exc,
        )
        # Fallback to local SQLite async DB
        global _engine, _session_maker
        Path("data").mkdir(parents=True, exist_ok=True)
        fallback_url = "sqlite+aiosqlite:///data/contractguard.db"
        _engine = create_async_engine(fallback_url, echo=False, future=True)
        _session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Local SQLite async database schema successfully initialized.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
