"""Database session and engine configuration."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from backend.src.config.settings import get_settings


def create_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine with connection pooling."""
    settings = get_settings()

    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        echo=settings.debug,
    )


# Global engine instance
_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get async session maker bound to the engine."""
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session.

    Yields:
        AsyncSession: Database session that auto-commits on success
            and rolls back on exception.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of FastAPI.

    Useful for background workers and scripts.

    Yields:
        AsyncSession: Database session with auto-commit/rollback.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_engine() -> None:
    """Close the database engine and release connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


# =============================================================================
# Synchronous database session support (for Celery workers)
# =============================================================================

# Global sync engine instance
_sync_engine: Engine | None = None


def get_sync_engine() -> Engine:
    """Get or create the synchronous database engine."""
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        _sync_engine = create_sync_engine(
            settings.sync_database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            echo=settings.debug,
        )
    return _sync_engine


def get_sync_session_maker() -> sessionmaker[Session]:
    """Get sync session maker bound to the engine."""
    return sessionmaker(
        bind=get_sync_engine(),
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )


@contextmanager
def get_sync_session_context() -> Generator[Session, None, None]:
    """Context manager for synchronous database sessions.

    Useful for Celery workers and other sync contexts.

    Yields:
        Session: Database session with auto-commit/rollback.
    """
    session_maker = get_sync_session_maker()
    session = session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_sync_engine() -> None:
    """Close the synchronous database engine and release connections."""
    global _sync_engine
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
