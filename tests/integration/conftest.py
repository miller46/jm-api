"""Integration test fixtures — real uvicorn server + file-based SQLite."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jm_api.core.config import get_settings
from jm_api.db.base import Base

_SQLITE_PATH = Path("/tmp/jm_integration_test.db")
_DATABASE_URL = f"sqlite:///{_SQLITE_PATH}"


def _find_free_port() -> int:
    """Bind to port 0 on localhost to get a free port from the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def integration_server():
    """Start a real uvicorn server backed by a file-based SQLite DB.

    Yields the base URL (``http://127.0.0.1:<port>``).
    """
    # 1. Point the app at the integration test database.
    os.environ["JM_API_DATABASE_URL"] = _DATABASE_URL
    get_settings.cache_clear()

    settings = get_settings()

    # 2. Create tables.
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)

    # 3. Start uvicorn in a background thread.
    port = _find_free_port()
    config = uvicorn.Config(
        "jm_api.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=asyncio.run, args=(server.serve(),), daemon=True)
    thread.start()

    # 4. Wait until the server is ready.
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            resp = httpx.get(f"{base_url}/api/v1/healthz", timeout=1.0)
            if resp.status_code == 200:
                break
        except httpx.ConnectError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("Integration server did not become ready in time")

    yield base_url

    # 5. Teardown.
    server.should_exit = True
    thread.join(timeout=5)
    Base.metadata.drop_all(engine)
    engine.dispose()
    if _SQLITE_PATH.exists():
        _SQLITE_PATH.unlink()


@pytest.fixture(scope="session")
def base_url(integration_server: str) -> str:
    """Return the base URL of the running integration server."""
    return integration_server


@pytest.fixture
def http_client(base_url: str):
    """Yield an ``httpx.Client`` pointed at the integration server."""
    with httpx.Client(base_url=base_url) as client:
        yield client


@pytest.fixture
def db_session(integration_server: str):
    """Yield a SQLAlchemy Session connected to the integration database.

    Rolls back and closes on teardown so each test starts clean.
    """
    engine = create_engine(_DATABASE_URL)
    session = Session(bind=engine)
    yield session
    session.rollback()
    session.close()
    engine.dispose()
