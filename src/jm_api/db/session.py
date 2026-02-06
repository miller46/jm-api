from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jm_api.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI


def init_db(app: FastAPI) -> None:
    """Initialize database engine and session factory at startup.

    Stores engine and session factory in app.state for thread-safe access.
    Should be called during FastAPI lifespan startup.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory


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
