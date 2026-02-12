"""Tests for generic delete router factory using minimal Gadget model.

Mirrors the test pattern from test_generic_update_router.py: uses a
standalone Widget model so the generic delete factory is tested in
isolation from any specific resource (e.g. Bot).
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
    create_delete_router,
    create_read_router,
)
from jm_api.db.base import Base, TimestampedIdBase
from jm_api.db.session import get_db


# --- Test model and schemas ---


class Gadget(TimestampedIdBase):
    """Minimal model for testing generic delete router."""

    __tablename__ = "gadgets_delete"

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
    delete_router = create_delete_router(
        prefix="/gadgets",
        tags=["gadgets"],
        model=Gadget,
        resource_name="Gadget",
    )
    app.include_router(read_router)
    app.include_router(create_router)
    app.include_router(delete_router)
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


# --- Delete Endpoint Tests ---


class TestGenericDeleteSuccess:
    """Test that DELETE /{prefix}/{id} removes a record."""

    def test_delete_returns_204(self, gadget_client: TestClient) -> None:
        """Successful DELETE returns 204 No Content."""
        gadget = _create_gadget(gadget_client)
        response = gadget_client.delete(f"/gadgets/{gadget['id']}")
        assert response.status_code == 204

    def test_delete_returns_empty_body(self, gadget_client: TestClient) -> None:
        """Successful DELETE response has no body."""
        gadget = _create_gadget(gadget_client)
        response = gadget_client.delete(f"/gadgets/{gadget['id']}")
        assert response.content == b""

    def test_deleted_record_not_found_on_get(self, gadget_client: TestClient) -> None:
        """GET after DELETE returns 404."""
        gadget = _create_gadget(gadget_client)
        gadget_client.delete(f"/gadgets/{gadget['id']}")
        get_resp = gadget_client.get(f"/gadgets/{gadget['id']}")
        assert get_resp.status_code == 404

    def test_deleted_record_excluded_from_list(self, gadget_client: TestClient) -> None:
        """Deleted record does not appear in list endpoint."""
        g1 = _create_gadget(gadget_client, name="keep-me")
        g2 = _create_gadget(gadget_client, name="delete-me")
        gadget_client.delete(f"/gadgets/{g2['id']}")

        list_resp = gadget_client.get("/gadgets")
        ids = [item["id"] for item in list_resp.json()["items"]]
        assert g1["id"] in ids
        assert g2["id"] not in ids

    def test_delete_does_not_affect_other_records(
        self, gadget_client: TestClient
    ) -> None:
        """Deleting one record leaves others intact."""
        g_keep = _create_gadget(gadget_client, name="survivor")
        g_delete = _create_gadget(gadget_client, name="doomed")
        gadget_client.delete(f"/gadgets/{g_delete['id']}")

        get_resp = gadget_client.get(f"/gadgets/{g_keep['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "survivor"

    def test_list_count_decremented_after_delete(
        self, gadget_client: TestClient
    ) -> None:
        """Total count in list response decreases after deletion."""
        _create_gadget(gadget_client, name="one")
        g2 = _create_gadget(gadget_client, name="two")

        before = gadget_client.get("/gadgets").json()["total"]
        gadget_client.delete(f"/gadgets/{g2['id']}")
        after = gadget_client.get("/gadgets").json()["total"]

        assert after == before - 1


class TestGenericDeleteNotFound:
    """Test DELETE /{prefix}/{id} with nonexistent ID."""

    def test_nonexistent_returns_404(self, gadget_client: TestClient) -> None:
        """DELETE of nonexistent ID returns 404."""
        fake_id = "z" * 32
        response = gadget_client.delete(f"/gadgets/{fake_id}")
        assert response.status_code == 404

    def test_404_includes_resource_name_in_message(
        self, gadget_client: TestClient
    ) -> None:
        """404 message uses the configured resource_name."""
        fake_id = "z" * 32
        response = gadget_client.delete(f"/gadgets/{fake_id}")
        data = response.json()
        assert data["detail"]["message"] == "Gadget not found"

    def test_404_includes_requested_id(self, gadget_client: TestClient) -> None:
        """404 body includes the ID that was requested."""
        fake_id = "y" * 32
        response = gadget_client.delete(f"/gadgets/{fake_id}")
        data = response.json()
        assert data["detail"]["id"] == fake_id


class TestGenericDeleteIdempotency:
    """Test repeated deletes on the same record."""

    def test_second_delete_returns_404(self, gadget_client: TestClient) -> None:
        """Deleting an already-deleted record returns 404."""
        gadget = _create_gadget(gadget_client)
        first = gadget_client.delete(f"/gadgets/{gadget['id']}")
        assert first.status_code == 204

        second = gadget_client.delete(f"/gadgets/{gadget['id']}")
        assert second.status_code == 404


class TestGenericDeleteIdValidation:
    """Test path parameter validation on DELETE endpoint."""

    def test_short_id_rejected(self, gadget_client: TestClient) -> None:
        """ID shorter than 32 characters is rejected with 422."""
        response = gadget_client.delete("/gadgets/short")
        assert response.status_code == 422

    def test_long_id_rejected(self, gadget_client: TestClient) -> None:
        """ID longer than 32 characters is rejected with 422."""
        long_id = "a" * 33
        response = gadget_client.delete(f"/gadgets/{long_id}")
        assert response.status_code == 422

    def test_special_characters_rejected(self, gadget_client: TestClient) -> None:
        """ID with special characters is rejected with 422."""
        bad_id = "abc-def_ghi.jkl!mnopqrstuvwxyz12"
        response = gadget_client.delete(f"/gadgets/{bad_id}")
        assert response.status_code == 422

    def test_uppercase_letters_accepted(self, gadget_client: TestClient) -> None:
        """ID with uppercase letters passes validation (404, not 422)."""
        upper_id = "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        response = gadget_client.delete(f"/gadgets/{upper_id}")
        assert response.status_code == 404

    def test_mixed_case_alphanumeric_accepted(self, gadget_client: TestClient) -> None:
        """Mixed-case alphanumeric 32-char ID passes validation."""
        mixed_id = "aAbBcCdDeEfFgGhHiIjJkKlLmMnNoO01"
        response = gadget_client.delete(f"/gadgets/{mixed_id}")
        assert response.status_code == 404


class TestGenericDeleteRouteNaming:
    """Test that the factory produces correctly-named routes."""

    def test_route_function_name_includes_resource(self) -> None:
        """Delete route function is named after the resource."""
        router = create_delete_router(
            prefix="/gadgets",
            tags=["gadgets"],
            model=Gadget,
            resource_name="Gadget",
        )
        route_names = [route.name for route in router.routes]
        assert any("gadget" in name for name in route_names), (
            f"Expected resource name in route names, got: {route_names}"
        )

    def test_route_name_is_delete_prefixed(self) -> None:
        """Delete route name starts with 'delete_'."""
        router = create_delete_router(
            prefix="/gadgets",
            tags=["gadgets"],
            model=Gadget,
            resource_name="Gadget",
        )
        route_names = [route.name for route in router.routes]
        assert "delete_gadget" in route_names, (
            f"Expected 'delete_gadget' in route names, got: {route_names}"
        )


class TestGenericDeleteCustomIdPattern:
    """Test delete router with a custom ID regex pattern."""

    @pytest.fixture
    def custom_id_app(self, gadget_engine, gadget_session: Session) -> FastAPI:
        """App with a delete router that only accepts numeric IDs."""
        app = FastAPI()
        app.state.db_engine = gadget_engine
        app.state.db_session_factory = sessionmaker(bind=gadget_engine)

        def override_get_db():
            yield gadget_session

        app.dependency_overrides[get_db] = override_get_db

        delete_router = create_delete_router(
            prefix="/gadgets",
            tags=["gadgets"],
            model=Gadget,
            resource_name="Gadget",
            id_pattern=r"^[0-9]{8}$",
        )
        app.include_router(delete_router)
        return app

    @pytest.fixture
    def custom_id_client(self, custom_id_app: FastAPI) -> TestClient:
        return TestClient(custom_id_app)

    def test_custom_pattern_rejects_default_format(
        self, custom_id_client: TestClient
    ) -> None:
        """Default 32-char alphanumeric ID is rejected by numeric-only pattern."""
        default_id = "a" * 32
        response = custom_id_client.delete(f"/gadgets/{default_id}")
        assert response.status_code == 422

    def test_custom_pattern_accepts_matching_format(
        self, custom_id_client: TestClient
    ) -> None:
        """8-digit numeric ID passes custom validation (404, not 422)."""
        numeric_id = "12345678"
        response = custom_id_client.delete(f"/gadgets/{numeric_id}")
        assert response.status_code == 404


class TestGenericDeleteIdValidationEdgeCases:
    """Extended ID validation edge cases for DELETE endpoint."""

    def test_empty_string_id_returns_404_or_405(self, gadget_client: TestClient) -> None:
        """Empty string ID hits the collection endpoint, not the item endpoint."""
        response = gadget_client.delete("/gadgets/")
        # Empty path segment — either 404 (no route) or 405 (method not allowed)
        assert response.status_code in (404, 405)

    def test_numeric_only_32char_id_accepted(self, gadget_client: TestClient) -> None:
        """32-character all-numeric ID passes validation."""
        numeric_id = "1" * 32
        response = gadget_client.delete(f"/gadgets/{numeric_id}")
        assert response.status_code == 404  # valid format, record doesn't exist

    def test_unicode_characters_rejected(self, gadget_client: TestClient) -> None:
        """ID with unicode characters is rejected with 422."""
        unicode_id = "abcdefghijklmnopqrstuvwx\u00e9\u00e8\u00ea\u00eb\u00ec\u00ed\u00ee\u00ef"
        response = gadget_client.delete(f"/gadgets/{unicode_id}")
        assert response.status_code == 422

    def test_whitespace_only_id_rejected(self, gadget_client: TestClient) -> None:
        """ID consisting only of spaces is rejected."""
        response = gadget_client.delete("/gadgets/" + " " * 32)
        assert response.status_code == 422

    def test_sql_injection_in_id_rejected(self, gadget_client: TestClient) -> None:
        """SQL injection attempt in ID is rejected by regex validation."""
        response = gadget_client.delete("/gadgets/1'; DROP TABLE gadgets;--aaaa")
        assert response.status_code == 422


class TestGenericDeleteMultipleRecords:
    """Test delete behavior with multiple records present."""

    def test_delete_first_of_many(self, gadget_client: TestClient) -> None:
        """Deleting the first created record leaves others intact."""
        g1 = _create_gadget(gadget_client, name="first")
        g2 = _create_gadget(gadget_client, name="second")
        g3 = _create_gadget(gadget_client, name="third")

        gadget_client.delete(f"/gadgets/{g1['id']}")

        # Remaining records are accessible
        assert gadget_client.get(f"/gadgets/{g2['id']}").status_code == 200
        assert gadget_client.get(f"/gadgets/{g3['id']}").status_code == 200
        assert gadget_client.get(f"/gadgets/{g1['id']}").status_code == 404

    def test_delete_all_records_one_by_one(self, gadget_client: TestClient) -> None:
        """Deleting all records one by one empties the collection."""
        g1 = _create_gadget(gadget_client, name="one")
        g2 = _create_gadget(gadget_client, name="two")
        g3 = _create_gadget(gadget_client, name="three")

        for gid in [g1["id"], g2["id"], g3["id"]]:
            resp = gadget_client.delete(f"/gadgets/{gid}")
            assert resp.status_code == 204

        list_resp = gadget_client.get("/gadgets")
        assert list_resp.json()["total"] == 0
        assert list_resp.json()["items"] == []

    def test_create_after_delete_succeeds(self, gadget_client: TestClient) -> None:
        """New records can be created after deleting existing ones."""
        g1 = _create_gadget(gadget_client, name="original")
        gadget_client.delete(f"/gadgets/{g1['id']}")

        g2 = _create_gadget(gadget_client, name="replacement")
        assert g2["id"] != g1["id"]

        get_resp = gadget_client.get(f"/gadgets/{g2['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "replacement"

    def test_delete_does_not_reuse_id(self, gadget_client: TestClient) -> None:
        """Deleted record's ID is not reused for new records."""
        g1 = _create_gadget(gadget_client, name="original")
        deleted_id = g1["id"]
        gadget_client.delete(f"/gadgets/{deleted_id}")

        # Create several new records and verify none reuse the deleted ID
        new_ids = []
        for i in range(5):
            g = _create_gadget(gadget_client, name=f"new-{i}")
            new_ids.append(g["id"])

        assert deleted_id not in new_ids


class TestGenericDeleteResponseHeaders:
    """Test HTTP response details for DELETE endpoint."""

    def test_successful_delete_content_length_zero(
        self, gadget_client: TestClient
    ) -> None:
        """Successful 204 response has zero content length."""
        gadget = _create_gadget(gadget_client)
        response = gadget_client.delete(f"/gadgets/{gadget['id']}")
        assert response.status_code == 204
        assert len(response.content) == 0

    def test_404_response_is_json(self, gadget_client: TestClient) -> None:
        """404 error response has JSON content type."""
        fake_id = "z" * 32
        response = gadget_client.delete(f"/gadgets/{fake_id}")
        assert response.status_code == 404
        assert "application/json" in response.headers.get("content-type", "")

    def test_404_detail_structure_is_dict(self, gadget_client: TestClient) -> None:
        """404 response detail is a dict with message and id keys."""
        fake_id = "z" * 32
        response = gadget_client.delete(f"/gadgets/{fake_id}")
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert set(detail.keys()) == {"message", "id"}
