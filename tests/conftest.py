"""Shared test fixtures."""

from datetime import datetime

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from jm_api.db.base import Base
from jm_api.models.bot import Bot


@pytest.fixture
def db_engine():
    """Create in-memory SQLite engine for test isolation."""
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    """Create database session from test engine."""
    session = Session(db_engine)
    yield session
    session.close()


@pytest.fixture
def app(db_session: Session) -> FastAPI:
    """Create test app with overridden database dependency."""
    from jm_api.app import create_app
    from jm_api.db.session import get_db

    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def bot_factory(db_session: Session):
    """Factory fixture for creating bots in tests.

    Usage:
        def test_something(bot_factory):
            bot = bot_factory(rig_id="my-rig")
    """

    def _create_bot(
        rig_id: str = "rig-001",
        kill_switch: bool = False,
        last_run_log: str | None = None,
        last_run_at: datetime | None = None,
        create_at: datetime | None = None,
        last_update_at: datetime | None = None,
    ) -> Bot:
        """Create and persist a bot.

        Args:
            rig_id: Bot rig identifier
            kill_switch: Whether bot is killed
            last_run_log: Log from last run
            last_run_at: Timestamp of last run
            create_at: Override creation timestamp (for testing date filters)
            last_update_at: Override last update timestamp (for testing date filters)
        """
        bot = Bot(
            rig_id=rig_id,
            kill_switch=kill_switch,
            last_run_log=last_run_log,
            last_run_at=last_run_at,
        )
        db_session.add(bot)
        db_session.flush()  # Get the ID assigned

        # Override timestamps if specified (for deterministic date filter tests)
        updates = {}
        if create_at is not None:
            updates["create_at"] = create_at
        if last_update_at is not None:
            updates["last_update_at"] = last_update_at

        if updates:
            db_session.execute(
                sa.update(Bot)
                .where(Bot.id == bot.id)
                .values(**updates)
            )

        db_session.commit()
        db_session.refresh(bot)
        return bot

    return _create_bot
