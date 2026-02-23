from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from jm_api.core.config import get_settings
from jm_api.core.shutdown import (
    dispose_database_connections,
    drain_connections,
    register_signal_handlers,
)
from jm_api.db.migrations import assert_database_is_up_to_date
from jm_api.db.session import init_db

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.
    
    Handles startup initialization and graceful shutdown:
    - Registers signal handlers for SIGTERM/SIGINT
    - Initializes database connections
    - Performs graceful shutdown with connection draining on exit
    """
    # Startup
    logger.info("application.starting")
    register_signal_handlers()
    init_db(app)

    settings = get_settings()
    if settings.db_migration_check_enabled:
        assert_database_is_up_to_date(app.state.db_engine)

    logger.info("application.ready")

    yield

    # Shutdown - graceful shutdown with connection draining
    logger.info("application.shutting_down")
    drain_connections()
    dispose_database_connections(app)
    logger.info("application.shutdown_complete")
