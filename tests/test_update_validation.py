"""Tests for update router validation fixes from PR #34 review.

Covers:
  - Issue 1: Path validation on item_id in update endpoint
  - Issue 2: Rejection of None for non-nullable fields (kill_switch)
  - Issue 5: Default 200 status code (no explicit HTTP_200_OK needed)
"""

from __future__ import annotations

from datetime import datetime

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from jm_api.api.generic.filters import FilterField, FilterType
from jm_api.api.generic.router import (
    create_create_router,
    create_read_router,
    create_update_router,
)
from jm_api.db.base import Base, TimestampedIdBase
from jm_api.db.session import get_db


# --- Test model and schemas ---


class Gadget(TimestampedIdBase):
    """Minimal model for testing update validation."""

    __tablename__ = "gadgets_validation"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)


class GadgetResponse(BaseModel):
    id: str
    name: str
    active: bool
    description: str | None
    create_at: datetime
    last_update_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GadgetCreate(BaseModel):
    name: str
    active: bool = True
    description: str | None = None


class GadgetUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    description: str | None = None


# --- Fixtures ---


@pytest.fixture
def gadget_engine():
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def gadget_session(gadget_engine) -> Session:
    session = Session(gadget_engine)
    yield session
    session.close()


@pytest.fixture
def gadget_app(gadget_engine, gadget_session: Session) -> FastAPI:
    app = FastAPI()
    app.state.db_engine = gadget_engine
    app.state.db_session_factory = sessionmaker(bind=gadget_engine)

    def override_get_db():
        yield gadget_session

    app.dependency_overrides[get_db] = override_get_db

    read_router = create_read_router(
        prefix="/gadgets",
        tags=["gadgets"],
        model=Gadget,
        response_schema=GadgetResponse,
        filter_config=[FilterField("name", FilterType.EXACT)],
        resource_name="Gadget",
    )
    create_router = create_create_router(
        prefix="/gadgets",
        tags=["gadgets"],
        model=Gadget,
        response_schema=GadgetResponse,
        create_schema=GadgetCreate,
        resource_name="Gadget",
    )
    update_router = create_update_router(
        prefix="/gadgets",
        tags=["gadgets"],
        model=Gadget,
        response_schema=GadgetResponse,
        update_schema=GadgetUpdate,
        resource_name="Gadget",
    )
    app.include_router(read_router)
    app.include_router(create_router)
    app.include_router(update_router)
    return app


@pytest.fixture
def gadget_client(gadget_app: FastAPI) -> TestClient:
    return TestClient(gadget_app)


def _create_gadget(client: TestClient, **kwargs) -> dict:
    """Helper to create a gadget and return its JSON."""
    payload = {"name": "test-gadget", **kwargs}
    resp = client.post("/gadgets", json=payload)
    assert resp.status_code == 201
    return resp.json()


# ===================================================================
# Issue 1: Path validation on item_id in update endpoint
# ===================================================================


class TestUpdatePathValidation:
    """Update endpoint must validate item_id format like the read endpoint."""

    def test_update_rejects_invalid_id_with_special_chars(
        self, gadget_client: TestClient
    ) -> None:
        """PUT with special characters in ID returns 422 (path validation)."""
        invalid_id = "abc!@#$%^&*()_+=bad!!"
        response = gadget_client.put(
            f"/gadgets/{invalid_id}", json={"name": "hacked"}
        )
        assert response.status_code == 422

    def test_update_rejects_id_wrong_length(
        self, gadget_client: TestClient
    ) -> None:
        """PUT with ID of wrong length returns 422."""
        response = gadget_client.put(
            "/gadgets/tooshort", json={"name": "nope"}
        )
        assert response.status_code == 422

    def test_update_rejects_id_with_hyphens(
        self, gadget_client: TestClient
    ) -> None:
        """PUT with hyphens in ID returns 422 (only alphanumeric allowed)."""
        bad_id = "a1b2-c3d4-e5f6-g7h8-i9j0-k1l2m"  # 32 chars but has hyphens
        response = gadget_client.put(
            f"/gadgets/{bad_id}", json={"name": "nope"}
        )
        assert response.status_code == 422

    def test_update_accepts_valid_32char_alphanumeric_id(
        self, gadget_client: TestClient
    ) -> None:
        """PUT with valid 32-char alphanumeric ID proceeds (returns 404 for non-existent)."""
        valid_id = "a" * 32
        response = gadget_client.put(
            f"/gadgets/{valid_id}", json={"name": "ok"}
        )
        # Should pass validation but return 404 since gadget doesn't exist
        assert response.status_code == 404

    def test_read_and_update_have_consistent_validation(
        self, gadget_client: TestClient
    ) -> None:
        """GET and PUT should both reject the same invalid IDs."""
        invalid_id = "not-valid!"
        get_resp = gadget_client.get(f"/gadgets/{invalid_id}")
        put_resp = gadget_client.put(
            f"/gadgets/{invalid_id}", json={"name": "x"}
        )
        assert get_resp.status_code == put_resp.status_code == 422


# ===================================================================
# Issue 2: Reject None for non-nullable fields
# ===================================================================


class TestUpdateNullNonNullableField:
    """Update must reject null for non-nullable boolean fields."""

    def test_bot_update_rejects_null_kill_switch(
        self, client: TestClient, bot_factory
    ) -> None:
        """PUT with kill_switch=null returns 422 for non-nullable bool field."""
        bot = bot_factory(rig_id="rig-null-test")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"kill_switch": None}
        )
        assert response.status_code == 422

    def test_bot_update_rejects_null_rig_id(
        self, client: TestClient, bot_factory
    ) -> None:
        """PUT with rig_id=null returns 422 for non-nullable string field."""
        bot = bot_factory(rig_id="rig-null-test2")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"rig_id": None}
        )
        assert response.status_code == 422

    def test_bot_update_allows_null_for_nullable_field(
        self, client: TestClient, bot_factory
    ) -> None:
        """PUT with last_run_log=null succeeds (it's a nullable field)."""
        bot = bot_factory(rig_id="rig-nullable", last_run_log="some log")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"last_run_log": None}
        )
        assert response.status_code == 200
        assert response.json()["last_run_log"] is None

    def test_bot_update_still_accepts_valid_kill_switch(
        self, client: TestClient, bot_factory
    ) -> None:
        """PUT with kill_switch=true still works after adding validation."""
        bot = bot_factory(rig_id="rig-valid-ks", kill_switch=False)
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"kill_switch": True}
        )
        assert response.status_code == 200
        assert response.json()["kill_switch"] is True


# ===================================================================
# Issue 5: Default 200 status code (after removing explicit HTTP_200_OK)
# ===================================================================


class TestUpdateDefaultStatus:
    """Update endpoint returns 200 by default (no explicit status_code needed)."""

    def test_update_returns_200_without_explicit_status(
        self, gadget_client: TestClient
    ) -> None:
        """After removing explicit HTTP_200_OK, update still returns 200."""
        gadget = _create_gadget(gadget_client)
        response = gadget_client.put(
            f"/gadgets/{gadget['id']}", json={"name": "updated"}
        )
        assert response.status_code == 200
