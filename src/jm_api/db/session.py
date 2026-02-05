from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from jm_api.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache database engine."""
    settings = get_settings()
    return create_engine(settings.database_url)


@lru_cache
def get_session_factory() -> sessionmaker:
    """Create and cache session factory."""
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_engine(),
    )


def get_db() -> Generator[Session, None, None]:
    """Yield database session per request."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def reset_db_state() -> None:
    """Reset cached database state. Useful for testing."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
