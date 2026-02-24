from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from jm_api.api.deps import cleanup_expired_sessions
from jm_api.core.config import get_settings
from jm_api.core.redis_client import close_redis, init_redis
from jm_api.core.shutdown import (
    dispose_database_connections,
    drain_connections,
    register_signal_handlers,
)
from jm_api.db.migrations import assert_database_is_up_to_date
from jm_api.db.session import init_db

logger = structlog.get_logger(__name__)


async def _session_cleanup_loop(app: FastAPI) -> None:
    settings = get_settings()
    while True:
        try:
            with app.state.db_session_factory() as db:
                cleanup_expired_sessions(db)
        except Exception as exc:
            logger.warning("auth.session_cleanup.failed", error=str(exc))

        await asyncio.sleep(settings.session_cleanup_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.
    
    Handles startup initialization and graceful shutdown:
    - Registers signal handlers for SIGTERM/SIGINT
    - Initializes database connections
    - Initializes Redis connection (if configured)
    - Performs graceful shutdown with connection draining on exit
    """
    # Startup
    logger.info("application.starting")
    register_signal_handlers()
    init_db(app)

    settings = get_settings()
    if settings.db_migration_check_enabled:
        assert_database_is_up_to_date(app.state.db_engine)

    # Initialize Redis (if configured)
    try:
        init_redis(app)
    except Exception as exc:
        # Log but don't fail startup - Redis might be optional
        logger.warning("redis.startup_failed", error=str(exc))
        # If Redis is required for production, the app should fail fast
        # This allows development without Redis while still supporting it

    session_cleanup_task = asyncio.create_task(_session_cleanup_loop(app))

    logger.info("application.ready")

    yield

    session_cleanup_task.cancel()
    try:
        await session_cleanup_task
    except asyncio.CancelledError:
        pass

    # Shutdown - graceful shutdown with connection draining
    logger.info("application.shutting_down")
    drain_connections()
    dispose_database_connections(app)
    close_redis()
    logger.info("application.shutdown_complete")
