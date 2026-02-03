from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Application starting")
    yield
    logger.info("Application shutting down")
