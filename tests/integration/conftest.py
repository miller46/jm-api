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
from sqlalchemy import text

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

    The app's lifespan handler (``init_db``) creates the SQLAlchemy engine and
    session factory and stores them in ``app.state``.  After the server is
    ready we import the module-level ``app`` object and use its engine to
    create the schema tables — this guarantees a single shared engine for both
    the server and the test fixtures.
    """
    # 1. Point the app at the integration test database.
    os.environ["JM_API_DATABASE_URL"] = _DATABASE_URL
    get_settings.cache_clear()

    # 2. Start uvicorn in a background thread.
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

    # 3. Wait until the server is ready.
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

    # 4. Create schema tables using the app's own engine (single engine).
    # NOTE: The server is already accepting requests at this point, but no
    # test runs until this fixture yields.  If the app's lifespan ever adds
    # its own ``create_all`` call, this step becomes redundant (not harmful).
    from jm_api.main import app

    engine = app.state.db_engine
    Base.metadata.create_all(engine)

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
    """Yield a SQLAlchemy Session that shares the app's engine.

    Uses the same engine the server uses (via ``app.state``) so writes are
    immediately visible to the running application.  Rolls back and closes on
    teardown.
    """
    from jm_api.main import app

    session = app.state.db_session_factory()
    yield session
    session.rollback()
    session.close()


def _do_clean_bots_table() -> None:
    """Delete all rows from the bots table.

    Shared helper so the autouse fixture and the ``clean_bots_table`` fixture
    exercise the exact same code path.
    """
    from jm_api.main import app

    session = app.state.db_session_factory()
    try:
        session.execute(text("DELETE FROM bots"))
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_bots_table(integration_server: str):
    """Truncate the bots table *before* every test for full isolation.

    Uses the "clean before" pattern: each test starts with a guaranteed-empty
    table regardless of what the previous test did or how fixtures were torn
    down.  This avoids any dependency on teardown ordering between this fixture
    and ``db_session``.
    """
    _do_clean_bots_table()
    yield


@pytest.fixture
def clean_bots_table():
    """Expose the cleanup helper for tests that need to invoke it explicitly.

    Calls the same ``_do_clean_bots_table`` function that the autouse
    ``_clean_bots_table`` fixture uses, so tests exercise the fixture's real
    code path rather than duplicating the SQL inline.
    """
    return _do_clean_bots_table
