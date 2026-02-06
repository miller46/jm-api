from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from jm_api.db.session import close_db, init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting")
    init_db(app)
    yield
    close_db(app)
    logger.info("Application shutting down")
