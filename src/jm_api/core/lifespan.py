from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from jm_api.core.config import get_settings
from jm_api.db.migrations import assert_database_is_up_to_date
from jm_api.db.session import close_db, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting")
    init_db(app)

    settings = get_settings()
    if settings.db_migration_check_enabled:
        assert_database_is_up_to_date(app.state.db_engine)

    yield
    close_db(app)
    logger.info("Application shutting down")
