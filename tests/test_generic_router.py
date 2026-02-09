"""Tests for generic read router factory using a minimal Widget model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import String, Boolean, Text
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from jm_api.api.generic.filters import FilterField, FilterType
from jm_api.api.generic.router import create_read_router
from jm_api.db.base import Base, TimestampedIdBase
from jm_api.db.session import get_db
from jm_api.schemas.generic import ListResponse


# --- Test model and schema ---


class Widget(TimestampedIdBase):
    """Minimal model for testing generic router."""

    __tablename__ = "widgets_router"

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


class WidgetListResponse(ListResponse[WidgetResponse]):
    pass


# --- Filter config ---

WIDGET_FILTERS = [
    FilterField("name", FilterType.EXACT),
    FilterField("active", FilterType.EXACT, python_type=bool),
    FilterField("description", FilterType.ILIKE, param_name="desc_search"),
    FilterField("create_at", FilterType.DATE_RANGE),
]


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

    widget_router = create_read_router(
        prefix="/widgets",
        tags=["widgets"],
        model=Widget,
        response_schema=WidgetResponse,
        filter_config=WIDGET_FILTERS,
        resource_name="Widget",
    )
    app.include_router(widget_router)
    return app


@pytest.fixture
def widget_client(widget_app: FastAPI) -> TestClient:
    return TestClient(widget_app)


@pytest.fixture
def widget_factory(widget_session: Session):
    def _create(
        name: str = "widget",
        active: bool = True,
        description: str | None = None,
        create_at: datetime | None = None,
    ) -> Widget:
        w = Widget(name=name, active=active, description=description)
        widget_session.add(w)
        widget_session.flush()
        if create_at is not None:
            widget_session.execute(
                sa.update(Widget).where(Widget.id == w.id).values(create_at=create_at)
            )
        widget_session.commit()
        widget_session.refresh(w)
        return w

    return _create


# --- List Endpoint Tests ---


class TestGenericListEmpty:
    def test_empty_list(self, widget_client: TestClient) -> None:
        """Empty database returns correct structure."""
        response = widget_client.get("/widgets")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert data["pages"] == 0


class TestGenericListPagination:
    def test_page_1(self, widget_client: TestClient, widget_factory) -> None:
        """Page 1 returns correct count and metadata."""
        for i in range(25):
            widget_factory(name=f"w-{i:03d}")

        response = widget_client.get("/widgets")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 20
        assert data["total"] == 25
        assert data["pages"] == 2

    def test_page_2(self, widget_client: TestClient, widget_factory) -> None:
        """Page 2 returns remaining items."""
        for i in range(25):
            widget_factory(name=f"w-{i:03d}")

        response = widget_client.get("/widgets", params={"page": 2})
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 25

    def test_per_page_over_max(self, widget_client: TestClient) -> None:
        """per_page > 100 returns 422."""
        response = widget_client.get("/widgets", params={"per_page": 101})
        assert response.status_code == 422

    def test_per_page_zero(self, widget_client: TestClient) -> None:
        """per_page=0 returns 422."""
        response = widget_client.get("/widgets", params={"per_page": 0})
        assert response.status_code == 422

    def test_page_zero(self, widget_client: TestClient) -> None:
        """page=0 returns 422."""
        response = widget_client.get("/widgets", params={"page": 0})
        assert response.status_code == 422

    def test_page_beyond_last(self, widget_client: TestClient, widget_factory) -> None:
        """Page beyond last returns empty items with correct metadata."""
        for i in range(3):
            widget_factory(name=f"w-{i}")
        response = widget_client.get("/widgets", params={"page": 999})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3


class TestGenericListFilters:
    def test_exact_filter(self, widget_client: TestClient, widget_factory) -> None:
        """EXACT filter works through the endpoint."""
        widget_factory(name="alpha")
        widget_factory(name="beta")
        widget_factory(name="alpha")

        response = widget_client.get("/widgets", params={"name": "alpha"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_bool_filter(self, widget_client: TestClient, widget_factory) -> None:
        """Bool EXACT filter works through the endpoint."""
        widget_factory(name="a", active=True)
        widget_factory(name="b", active=False)

        response = widget_client.get("/widgets", params={"active": False})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "b"

    def test_ilike_filter(self, widget_client: TestClient, widget_factory) -> None:
        """ILIKE filter works via param_name alias."""
        widget_factory(name="a", description="ERROR occurred")
        widget_factory(name="b", description="success")

        response = widget_client.get("/widgets", params={"desc_search": "error"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_date_range_filter(self, widget_client: TestClient, widget_factory) -> None:
        """DATE_RANGE filter works via _after/_before params."""
        old = datetime(2024, 1, 1, tzinfo=timezone.utc)
        new = datetime(2024, 6, 1, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, tzinfo=timezone.utc)

        widget_factory(name="old", create_at=old)
        widget_factory(name="new", create_at=new)

        response = widget_client.get(
            "/widgets", params={"create_at_after": cutoff.isoformat()}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "new"

    def test_combined_filters(self, widget_client: TestClient, widget_factory) -> None:
        """Multiple filters combine with AND logic."""
        widget_factory(name="alpha", active=True, description="error found")
        widget_factory(name="alpha", active=False, description="error found")
        widget_factory(name="beta", active=True, description="error found")

        response = widget_client.get(
            "/widgets", params={"name": "alpha", "active": True, "desc_search": "error"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_no_results(self, widget_client: TestClient, widget_factory) -> None:
        """Filter with no matches returns 200 and empty items."""
        widget_factory(name="alpha")
        response = widget_client.get("/widgets", params={"name": "nonexistent"})
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestGenericListSorting:
    def test_sorted_newest_first(self, widget_client: TestClient, widget_factory) -> None:
        """Items are sorted by create_at DESC, id DESC."""
        w1 = widget_factory(name="first")
        w2 = widget_factory(name="second")
        w3 = widget_factory(name="third")

        response = widget_client.get("/widgets")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["id"] == w3.id
        assert data["items"][1]["id"] == w2.id
        assert data["items"][2]["id"] == w1.id

    def test_deterministic_ordering(self, widget_client: TestClient, widget_factory) -> None:
        """Multiple fetches return same order."""
        for i in range(5):
            widget_factory(name=f"w-{i}")

        r1 = widget_client.get("/widgets")
        r2 = widget_client.get("/widgets")
        ids1 = [item["id"] for item in r1.json()["items"]]
        ids2 = [item["id"] for item in r2.json()["items"]]
        assert ids1 == ids2


# --- Get-by-ID Tests ---


class TestGenericGetById:
    def test_get_found(self, widget_client: TestClient, widget_factory) -> None:
        """Get existing item returns all fields."""
        w = widget_factory(name="test-widget", active=True, description="hello")
        response = widget_client.get(f"/widgets/{w.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == w.id
        assert data["name"] == "test-widget"
        assert data["active"] is True
        assert data["description"] == "hello"
        assert "create_at" in data
        assert "last_update_at" in data

    def test_get_not_found(self, widget_client: TestClient) -> None:
        """Nonexistent ID returns 404 with standard error structure."""
        nonexistent_id = "aaaabbbbccccddddeeeeffffgggghhhh"
        response = widget_client.get(f"/widgets/{nonexistent_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["message"] == "Widget not found"
        assert data["detail"]["id"] == nonexistent_id

    def test_get_invalid_id_too_short(self, widget_client: TestClient) -> None:
        """Short ID returns 422."""
        response = widget_client.get("/widgets/abc123")
        assert response.status_code == 422

    def test_get_invalid_id_too_long(self, widget_client: TestClient) -> None:
        """33-char ID returns 422."""
        response = widget_client.get(f"/widgets/{'a' * 33}")
        assert response.status_code == 422

    def test_get_invalid_id_special_chars(self, widget_client: TestClient) -> None:
        """ID with special characters returns 422."""
        response = widget_client.get("/widgets/abc-123-def-456-ghi-789-jkl-012")
        assert response.status_code == 422


# --- ListResponse Schema Tests ---


class TestListResponseSchema:
    def test_list_response_generic(self) -> None:
        """ListResponse[T] works with arbitrary schema."""
        resp = WidgetListResponse(
            items=[],
            total=0,
            page=1,
            per_page=20,
            pages=0,
        )
        assert resp.items == []
        assert resp.total == 0

    def test_list_response_with_items(self) -> None:
        """ListResponse[T] holds typed items."""
        now = datetime.now(timezone.utc)
        item = WidgetResponse(
            id="test123",
            name="w",
            active=True,
            description=None,
            create_at=now,
            last_update_at=now,
        )
        resp = WidgetListResponse(
            items=[item],
            total=1,
            page=1,
            per_page=20,
            pages=1,
        )
        assert len(resp.items) == 1
        assert resp.items[0].name == "w"


# --- PR Review Fix Tests ---


class TestCustomSortColumns:
    """Test that sort_columns parameter allows overriding default sort order."""

    def test_custom_sort_by_name_asc(
        self, widget_engine, widget_session: Session
    ) -> None:
        """Custom sort_columns overrides default create_at DESC ordering."""
        app = FastAPI()
        app.state.db_engine = widget_engine
        app.state.db_session_factory = sessionmaker(bind=widget_engine)

        def override_get_db():
            yield widget_session

        app.dependency_overrides[get_db] = override_get_db

        router = create_read_router(
            prefix="/widgets",
            tags=["widgets"],
            model=Widget,
            response_schema=WidgetResponse,
            filter_config=WIDGET_FILTERS,
            resource_name="Widget",
            sort_columns=[("name", "asc")],
        )
        app.include_router(router)
        client = TestClient(app)

        # Create widgets with names in non-alphabetical order
        w_c = Widget(name="charlie", active=True)
        w_a = Widget(name="alpha", active=True)
        w_b = Widget(name="bravo", active=True)
        widget_session.add_all([w_c, w_a, w_b])
        widget_session.commit()

        response = client.get("/widgets")
        assert response.status_code == 200
        data = response.json()
        names = [item["name"] for item in data["items"]]
        assert names == ["alpha", "bravo", "charlie"]

    def test_default_sort_is_create_at_desc_id_desc(
        self, widget_client: TestClient, widget_factory
    ) -> None:
        """Default sort (no sort_columns) remains create_at DESC, id DESC."""
        w1 = widget_factory(name="first")
        widget_factory(name="second")
        w3 = widget_factory(name="third")

        response = widget_client.get("/widgets")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["id"] == w3.id
        assert data["items"][2]["id"] == w1.id


class TestListEndpointResponseModel:
    """Test that list endpoint declares response_model for OpenAPI docs."""

    def test_list_endpoint_has_response_model_in_openapi(
        self, widget_app: FastAPI
    ) -> None:
        """List endpoint's OpenAPI schema includes response body schema."""
        client = TestClient(widget_app)
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        # The list endpoint should have a documented 200 response with content schema
        list_path = schema["paths"]["/widgets"]["get"]
        resp_200 = list_path["responses"]["200"]
        assert "content" in resp_200
        # The schema should reference a model with "items", "total", etc.
        resp_schema = resp_200["content"]["application/json"]["schema"]
        # It should have properties or $ref — either way, not be empty/missing
        assert "$ref" in resp_schema or "properties" in resp_schema


class TestUniqueRouteNames:
    """Test that routers produce resource-specific function names."""

    def test_route_function_names_include_resource_name(self) -> None:
        """Route functions are named after the resource for clear OpenAPI operation_ids."""
        router = create_read_router(
            prefix="/widgets",
            tags=["widgets"],
            model=Widget,
            response_schema=WidgetResponse,
            filter_config=WIDGET_FILTERS,
            resource_name="Widget",
        )

        route_names = [route.name for route in router.routes]
        # Function names should include the resource name, not generic "list_items"/"get_item"
        assert "list_items" not in route_names, "list function should be resource-specific"
        assert "get_item" not in route_names, "get function should be resource-specific"
        assert any("widget" in name for name in route_names), (
            f"Expected resource name in route names, got: {route_names}"
        )


class TestUniqueFilterParamsClassName:
    """Test that make_filter_dependency produces unique class names."""

    def test_different_resource_names_produce_different_class_names(self) -> None:
        """make_filter_dependency with different resource names creates distinct classes."""
        from jm_api.api.generic.filters import make_filter_dependency

        config = [FilterField("name", FilterType.EXACT)]

        cls_a = make_filter_dependency(config, resource_name="Widget")
        cls_b = make_filter_dependency(config, resource_name="Gadget")

        assert cls_a.__name__ != cls_b.__name__
        assert "Widget" in cls_a.__name__
        assert "Gadget" in cls_b.__name__
