"""Tests for generic create router factory using minimal Widget model."""

from __future__ import annotations

from datetime import datetime

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from jm_api.api.generic.filters import FilterField, FilterType
from jm_api.api.generic.router import create_read_router, create_create_router
from jm_api.db.base import Base, TimestampedIdBase
from jm_api.db.session import get_db


# --- Test model and schemas ---


class Gadget(TimestampedIdBase):
    """Minimal model for testing generic create router."""

    __tablename__ = "gadgets_create"
    __table_args__ = (UniqueConstraint("name", name="uq_gadgets_name"),)

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
    app.include_router(read_router)
    app.include_router(create_router)
    return app


@pytest.fixture
def gadget_client(gadget_app: FastAPI) -> TestClient:
    return TestClient(gadget_app)


# --- Create Endpoint Tests ---


class TestGenericCreateSuccess:
    def test_create_returns_201(self, gadget_client: TestClient) -> None:
        """Successful POST returns 201."""
        response = gadget_client.post("/gadgets", json={"name": "widget-1"})
        assert response.status_code == 201

    def test_create_returns_all_fields(self, gadget_client: TestClient) -> None:
        """Created item response includes all fields."""
        response = gadget_client.post("/gadgets", json={"name": "widget-1"})
        data = response.json()
        expected_fields = {"id", "name", "active", "description", "create_at", "last_update_at"}
        assert set(data.keys()) == expected_fields

    def test_create_with_defaults(self, gadget_client: TestClient) -> None:
        """Created item uses defaults for optional fields."""
        response = gadget_client.post("/gadgets", json={"name": "widget-1"})
        data = response.json()
        assert data["name"] == "widget-1"
        assert data["active"] is True
        assert data["description"] is None

    def test_create_with_all_fields(self, gadget_client: TestClient) -> None:
        """Created item with all fields set."""
        payload = {"name": "widget-full", "active": False, "description": "A test gadget"}
        response = gadget_client.post("/gadgets", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "widget-full"
        assert data["active"] is False
        assert data["description"] == "A test gadget"

    def test_create_auto_generates_id(self, gadget_client: TestClient) -> None:
        """Auto-managed id field is generated."""
        response = gadget_client.post("/gadgets", json={"name": "widget-id"})
        data = response.json()
        assert data["id"] is not None
        assert len(data["id"]) == 32

    def test_create_auto_generates_timestamps(self, gadget_client: TestClient) -> None:
        """Auto-managed timestamp fields are set."""
        response = gadget_client.post("/gadgets", json={"name": "widget-ts"})
        data = response.json()
        assert data["create_at"] is not None
        assert data["last_update_at"] is not None

    def test_created_item_persisted(self, gadget_client: TestClient) -> None:
        """Created item appears in list endpoint."""
        gadget_client.post("/gadgets", json={"name": "widget-persisted"})
        response = gadget_client.get("/gadgets")
        items = response.json()["items"]
        assert any(item["name"] == "widget-persisted" for item in items)


class TestGenericCreateValidation:
    def test_missing_required_field(self, gadget_client: TestClient) -> None:
        """Missing required field returns 422."""
        response = gadget_client.post("/gadgets", json={})
        assert response.status_code == 422

    def test_empty_body(self, gadget_client: TestClient) -> None:
        """Empty body returns 422."""
        response = gadget_client.post(
            "/gadgets",
            content="",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestGenericCreateRouteNaming:
    def test_route_function_name_includes_resource(self) -> None:
        """Create route function is named after the resource."""
        router = create_create_router(
            prefix="/gadgets",
            tags=["gadgets"],
            model=Gadget,
            response_schema=GadgetResponse,
            create_schema=GadgetCreate,
            resource_name="Gadget",
        )
        route_names = [route.name for route in router.routes]
        assert any("gadget" in name for name in route_names), (
            f"Expected resource name in route names, got: {route_names}"
        )


class TestGenericCreateIntegrityError:
    """Test that database integrity errors are handled gracefully."""

    def test_duplicate_unique_field_returns_409(self, gadget_client: TestClient) -> None:
        """Duplicate unique field returns 409 Conflict instead of 500."""
        gadget_client.post("/gadgets", json={"name": "unique-gadget"})
        response = gadget_client.post("/gadgets", json={"name": "unique-gadget"})
        assert response.status_code == 409

    def test_duplicate_unique_field_returns_error_detail(
        self, gadget_client: TestClient
    ) -> None:
        """Duplicate unique field returns a meaningful error message."""
        gadget_client.post("/gadgets", json={"name": "unique-gadget-2"})
        response = gadget_client.post("/gadgets", json={"name": "unique-gadget-2"})
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)
        assert len(data["detail"]) > 0

    def test_session_usable_after_integrity_error(
        self, gadget_client: TestClient
    ) -> None:
        """Session remains usable after an IntegrityError is handled."""
        gadget_client.post("/gadgets", json={"name": "gadget-a"})
        # Trigger integrity error
        response = gadget_client.post("/gadgets", json={"name": "gadget-a"})
        assert response.status_code == 409
        # Session should still work for subsequent requests
        response = gadget_client.post("/gadgets", json={"name": "gadget-b"})
        assert response.status_code == 201
        assert response.json()["name"] == "gadget-b"


class TestGenericCreateOpenAPISchema:
    """Test that the OpenAPI spec exposes create schema fields for field discovery."""

    def test_openapi_has_create_schema(self, gadget_client: TestClient) -> None:
        """OpenAPI spec includes GadgetCreate schema."""
        response = gadget_client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        schemas = schema.get("components", {}).get("schemas", {})
        assert "GadgetCreate" in schemas

    def test_create_schema_has_only_editable_fields(
        self, gadget_client: TestClient
    ) -> None:
        """Create schema contains only user-editable fields, not auto-managed ones."""
        response = gadget_client.get("/openapi.json")
        schema = response.json()
        gadget_create = schema["components"]["schemas"]["GadgetCreate"]
        props = set(gadget_create.get("properties", {}).keys())
        assert props == {"name", "active", "description"}

    def test_create_schema_excludes_auto_fields(
        self, gadget_client: TestClient
    ) -> None:
        """Create schema does not contain auto-managed fields."""
        response = gadget_client.get("/openapi.json")
        schema = response.json()
        gadget_create = schema["components"]["schemas"]["GadgetCreate"]
        props = set(gadget_create.get("properties", {}).keys())
        auto_fields = {"id", "create_at", "last_update_at"}
        assert props.isdisjoint(auto_fields), (
            f"Auto-managed fields found in create schema: {props & auto_fields}"
        )

    def test_post_endpoint_references_create_schema(
        self, gadget_client: TestClient
    ) -> None:
        """POST /gadgets references GadgetCreate as request body schema."""
        response = gadget_client.get("/openapi.json")
        schema = response.json()
        post_path = schema.get("paths", {}).get("/gadgets", {}).get("post", {})
        req_body = post_path.get("requestBody", {})
        json_schema = (
            req_body.get("content", {}).get("application/json", {}).get("schema", {})
        )
        ref = json_schema.get("$ref", "")
        assert "GadgetCreate" in ref
