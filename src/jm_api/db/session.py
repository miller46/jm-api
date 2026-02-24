from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jm_api.core.config import get_settings
from jm_api.core.observability import instrument_sqlalchemy

if TYPE_CHECKING:
    from fastapi import FastAPI

# Global session factory for use outside of request context (e.g., workers)
_SessionLocal: sessionmaker | None = None


def _build_engine_kwargs(database_url: str) -> dict:
    """Build SQLAlchemy engine kwargs with DB-specific connection options."""
    is_sqlite = database_url.startswith("sqlite")
    connect_args: dict[str, str | bool] = (
        {"check_same_thread": False}
        if is_sqlite
        else {
            # 30s timeout prevents runaway PostgreSQL queries from holding
            # a pooled connection indefinitely.
            "options": "-c statement_timeout=30000",
        }
    )
    engine_kwargs: dict = {"connect_args": connect_args}
    if not is_sqlite:
        engine_kwargs.update(
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    return engine_kwargs


def _get_session_maker() -> sessionmaker:
    """Get or create the session maker."""
    global _SessionLocal
    if _SessionLocal is None:
        settings = get_settings()
        engine_kwargs = _build_engine_kwargs(settings.database_url)
        engine = create_engine(settings.database_url, **engine_kwargs)
        instrument_sqlalchemy(engine, settings)
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
        )
    return _SessionLocal


def init_db(app: FastAPI) -> None:
    """Initialize database engine and session factory at startup.

    Stores engine and session factory in app.state for thread-safe access.
    Should be called during FastAPI lifespan startup.
    """
    settings = get_settings()
    engine_kwargs = _build_engine_kwargs(settings.database_url)
    engine = create_engine(settings.database_url, **engine_kwargs)
    instrument_sqlalchemy(engine, settings)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    # Also set global for non-request usage
    global _SessionLocal
    _SessionLocal = session_factory


def close_db(app: FastAPI) -> None:
    """Dispose database engine at shutdown.

    Should be called during FastAPI lifespan shutdown.
    """
    if hasattr(app.state, "db_engine"):
        app.state.db_engine.dispose()


def get_db(request: Request) -> Generator[Session, None, None]:
    """Yield database session per request.

    Uses session factory stored in app.state during lifespan startup.
    """
    session_factory: sessionmaker = request.app.state.db_session_factory
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Provide a SessionLocal for non-request contexts (e.g., workers)
def SessionLocal() -> Session:
    """Create a new database session for use outside of request context.
    
    This is useful for background workers and CLI commands.
    """
    session_maker = _get_session_maker()
    return session_maker()
