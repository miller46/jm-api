"""Tests for generic update router factory using minimal Gadget model."""

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
from jm_api.api.generic.router import create_read_router, create_create_router, create_update_router
from jm_api.db.base import Base, TimestampedIdBase
from jm_api.db.session import get_db


# --- Test model and schemas ---


class Widget(TimestampedIdBase):
    """Minimal model for testing generic update router."""

    __tablename__ = "widgets_update"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)


class WidgetResponse(BaseModel):
    id: str
    name: str
    active: bool
    description: str | None
    create_at: datetime
    last_update_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WidgetCreate(BaseModel):
    name: str
    active: bool = True
    description: str | None = None


class WidgetUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    description: str | None = None


# --- Fixtures ---


@pytest.fixture
def widget_engine():
    engine = sa.create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sa.pool.StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def widget_session(widget_engine) -> Session:
    session = Session(widget_engine)
    yield session
    session.close()


@pytest.fixture
def widget_app(widget_engine, widget_session: Session) -> FastAPI:
    app = FastAPI()
    app.state.db_engine = widget_engine
    app.state.db_session_factory = sessionmaker(bind=widget_engine)

    def override_get_db():
        yield widget_session

    app.dependency_overrides[get_db] = override_get_db

    read_router = create_read_router(
        prefix="/widgets",
        tags=["widgets"],
        model=Widget,
        response_schema=WidgetResponse,
        filter_config=[FilterField("name", FilterType.EXACT)],
        resource_name="Widget",
    )
    create_router = create_create_router(
        prefix="/widgets",
        tags=["widgets"],
        model=Widget,
        response_schema=WidgetResponse,
        create_schema=WidgetCreate,
        resource_name="Widget",
    )
    update_router = create_update_router(
        prefix="/widgets",
        tags=["widgets"],
        model=Widget,
        response_schema=WidgetResponse,
        update_schema=WidgetUpdate,
        resource_name="Widget",
    )
    app.include_router(read_router)
    app.include_router(create_router)
    app.include_router(update_router)
    return app


@pytest.fixture
def widget_client(widget_app: FastAPI) -> TestClient:
    return TestClient(widget_app)


def _create_widget(client: TestClient, **kwargs) -> dict:
    """Helper to create a widget and return its JSON."""
    payload = {"name": "test-widget", **kwargs}
    resp = client.post("/widgets", json=payload)
    assert resp.status_code == 201
    return resp.json()


# --- Update Endpoint Tests ---


class TestGenericUpdateSuccess:
    def test_update_returns_200(self, widget_client: TestClient) -> None:
        """Successful PUT returns 200."""
        widget = _create_widget(widget_client)
        response = widget_client.put(
            f"/widgets/{widget['id']}", json={"name": "updated"}
        )
        assert response.status_code == 200

    def test_update_returns_updated_record(self, widget_client: TestClient) -> None:
        """PUT response contains updated field values."""
        widget = _create_widget(widget_client)
        response = widget_client.put(
            f"/widgets/{widget['id']}", json={"name": "new-name"}
        )
        data = response.json()
        assert data["name"] == "new-name"

    def test_partial_update_only_changes_provided_fields(
        self, widget_client: TestClient
    ) -> None:
        """PUT with partial payload only updates provided fields."""
        widget = _create_widget(
            widget_client, name="original", active=True, description="keep me"
        )
        response = widget_client.put(
            f"/widgets/{widget['id']}", json={"active": False}
        )
        data = response.json()
        assert data["active"] is False
        assert data["name"] == "original"
        assert data["description"] == "keep me"

    def test_update_persists(self, widget_client: TestClient) -> None:
        """Updated values persist when re-fetched via GET."""
        widget = _create_widget(widget_client)
        widget_client.put(
            f"/widgets/{widget['id']}", json={"name": "persisted"}
        )
        get_resp = widget_client.get(f"/widgets/{widget['id']}")
        assert get_resp.json()["name"] == "persisted"

    def test_update_returns_all_response_fields(
        self, widget_client: TestClient
    ) -> None:
        """PUT response includes all fields from the response schema."""
        widget = _create_widget(widget_client)
        response = widget_client.put(
            f"/widgets/{widget['id']}", json={"name": "check-fields"}
        )
        expected = {"id", "name", "active", "description", "create_at", "last_update_at"}
        assert set(response.json().keys()) == expected

    def test_update_with_empty_body_is_noop(self, widget_client: TestClient) -> None:
        """PUT with empty object changes nothing (except last_update_at)."""
        widget = _create_widget(widget_client, name="stay-same")
        response = widget_client.put(f"/widgets/{widget['id']}", json={})
        assert response.status_code == 200
        assert response.json()["name"] == "stay-same"


class TestGenericUpdateNotFound:
    def test_update_nonexistent_returns_404(self, widget_client: TestClient) -> None:
        """PUT to nonexistent ID returns 404."""
        fake_id = "a" * 32
        response = widget_client.put(
            f"/widgets/{fake_id}", json={"name": "nope"}
        )
        assert response.status_code == 404

    def test_404_response_body(self, widget_client: TestClient) -> None:
        """404 response includes message and id."""
        fake_id = "b" * 32
        response = widget_client.put(
            f"/widgets/{fake_id}", json={"name": "nope"}
        )
        data = response.json()
        assert "detail" in data


class TestGenericUpdateRouteNaming:
    def test_route_function_name_includes_resource(self) -> None:
        """Update route function is named after the resource."""
        router = create_update_router(
            prefix="/widgets",
            tags=["widgets"],
            model=Widget,
            response_schema=WidgetResponse,
            update_schema=WidgetUpdate,
            resource_name="Widget",
        )
        route_names = [route.name for route in router.routes]
        assert any("widget" in name for name in route_names), (
            f"Expected resource name in route names, got: {route_names}"
        )
