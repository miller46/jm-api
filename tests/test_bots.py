"""Tests for Bot read API endpoints."""

from datetime import datetime, timedelta, timezone

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


def create_bot(
    session: Session,
    rig_id: str = "rig-001",
    kill_switch: bool = False,
    last_run_log: str | None = None,
    last_run_at: datetime | None = None,
) -> Bot:
    """Helper to create and persist a bot."""
    bot = Bot(
        rig_id=rig_id,
        kill_switch=kill_switch,
        last_run_log=last_run_log,
        last_run_at=last_run_at,
    )
    session.add(bot)
    session.commit()
    session.refresh(bot)
    return bot


# --- List Endpoint Tests ---


class TestListBotsEmpty:
    """Test GET /api/v1/bots with no data."""

    def test_list_bots_empty(self, client: TestClient) -> None:
        """Empty database returns correct structure with zero items."""
        # Act
        response = client.get("/api/v1/bots")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert data["pages"] == 0


class TestListBotsPagination:
    """Test pagination behavior."""

    def test_list_bots_paginated_page_1(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Page 1 of 25 bots returns 20 items with correct metadata."""
        # Arrange
        for i in range(25):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 20
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["per_page"] == 20
        assert data["pages"] == 2

    def test_list_bots_paginated_page_2(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Page 2 of 25 bots returns remaining 5 items."""
        # Arrange
        for i in range(25):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"page": 2})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 25
        assert data["page"] == 2
        assert data["pages"] == 2

    def test_list_bots_per_page_max_capped(
        self, client: TestClient, db_session: Session
    ) -> None:
        """per_page exceeding 100 is capped at 100."""
        # Arrange
        for i in range(150):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 200})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 100
        assert data["per_page"] == 100

    def test_list_bots_per_page_zero_invalid(self, client: TestClient) -> None:
        """per_page=0 returns 422 validation error."""
        # Act
        response = client.get("/api/v1/bots", params={"per_page": 0})

        # Assert
        assert response.status_code == 422

    def test_list_bots_page_zero_invalid(self, client: TestClient) -> None:
        """page=0 returns 422 validation error."""
        # Act
        response = client.get("/api/v1/bots", params={"page": 0})

        # Assert
        assert response.status_code == 422

    def test_pagination_pages_exact_division(
        self, client: TestClient, db_session: Session
    ) -> None:
        """40 bots with per_page=20 gives pages=2."""
        # Arrange
        for i in range(40):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 40
        assert data["pages"] == 2

    def test_pagination_pages_with_remainder(
        self, client: TestClient, db_session: Session
    ) -> None:
        """41 bots with per_page=20 gives pages=3."""
        # Arrange
        for i in range(41):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 41
        assert data["pages"] == 3

    def test_pagination_single_page(
        self, client: TestClient, db_session: Session
    ) -> None:
        """10 bots with per_page=20 gives pages=1."""
        # Arrange
        for i in range(10):
            create_bot(db_session, rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 10
        assert data["pages"] == 1


class TestListBotsFilters:
    """Test filtering functionality."""

    def test_filter_by_rig_id(self, client: TestClient, db_session: Session) -> None:
        """Filter by rig_id returns only matching bots."""
        # Arrange
        create_bot(db_session, rig_id="rig-001")
        create_bot(db_session, rig_id="rig-002")
        create_bot(db_session, rig_id="rig-001")

        # Act
        response = client.get("/api/v1/bots", params={"rig_id": "rig-001"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["rig_id"] == "rig-001" for item in data["items"])

    def test_filter_by_kill_switch_true(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by kill_switch=true returns only killed bots."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", kill_switch=True)
        create_bot(db_session, rig_id="rig-002", kill_switch=False)
        create_bot(db_session, rig_id="rig-003", kill_switch=True)

        # Act
        response = client.get("/api/v1/bots", params={"kill_switch": True})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["kill_switch"] is True for item in data["items"])

    def test_filter_by_kill_switch_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by kill_switch=false returns only active bots."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", kill_switch=True)
        create_bot(db_session, rig_id="rig-002", kill_switch=False)
        create_bot(db_session, rig_id="rig-003", kill_switch=False)

        # Act
        response = client.get("/api/v1/bots", params={"kill_switch": False})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["kill_switch"] is False for item in data["items"])

    def test_filter_by_log_search_case_insensitive(
        self, client: TestClient, db_session: Session
    ) -> None:
        """log_search matches case-insensitively."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", last_run_log="ERROR occurred")
        create_bot(db_session, rig_id="rig-002", last_run_log="error found")
        create_bot(db_session, rig_id="rig-003", last_run_log="Success")

        # Act
        response = client.get("/api/v1/bots", params={"log_search": "ERROR"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_filter_by_log_search_substring(
        self, client: TestClient, db_session: Session
    ) -> None:
        """log_search matches substrings."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", last_run_log="Task failed")
        create_bot(db_session, rig_id="rig-002", last_run_log="failure detected")
        create_bot(db_session, rig_id="rig-003", last_run_log="Success")

        # Act
        response = client.get("/api/v1/bots", params={"log_search": "fail"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_filter_no_results_returns_empty(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter with no matches returns 200 with empty items."""
        # Arrange
        create_bot(db_session, rig_id="rig-001")

        # Act
        response = client.get("/api/v1/bots", params={"rig_id": "nonexistent"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestListBotsDateFilters:
    """Test date range filtering."""

    def test_filter_create_at_after(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by create_at_after returns bots at or after timestamp."""
        # Arrange
        create_bot(db_session, rig_id="rig-001")
        bot2 = create_bot(db_session, rig_id="rig-002")

        # Act - use bot2's create_at as the cutoff (should include bot2)
        response = client.get(
            "/api/v1/bots", params={"create_at_after": bot2.create_at.isoformat()}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # bot2 should be included since filter is >=
        assert any(item["rig_id"] == "rig-002" for item in data["items"])

    def test_filter_create_at_before(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by create_at_before returns bots at or before timestamp."""
        # Arrange
        bot1 = create_bot(db_session, rig_id="rig-001")
        create_bot(db_session, rig_id="rig-002")

        # Act - use bot1's create_at as the cutoff (should include bot1)
        response = client.get(
            "/api/v1/bots", params={"create_at_before": bot1.create_at.isoformat()}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # bot1 should be included since filter is <=
        assert any(item["rig_id"] == "rig-001" for item in data["items"])

    def test_filter_create_at_range(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by create_at range returns bots within range (inclusive)."""
        # Arrange
        create_bot(db_session, rig_id="rig-001")
        bot2 = create_bot(db_session, rig_id="rig-002")

        # Act - filter for exactly bot2's timestamp
        response = client.get(
            "/api/v1/bots",
            params={
                "create_at_after": bot2.create_at.isoformat(),
                "create_at_before": bot2.create_at.isoformat(),
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        # Should find bot2 at minimum (exact match on both bounds)
        assert data["total"] >= 1
        assert any(item["rig_id"] == "rig-002" for item in data["items"])

    def test_filter_last_run_at_after(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by last_run_at_after returns bots that ran after timestamp."""
        # Arrange
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1, minutes=30)

        create_bot(db_session, rig_id="rig-001", last_run_at=past)
        create_bot(db_session, rig_id="rig-002", last_run_at=recent)
        create_bot(db_session, rig_id="rig-003", last_run_at=None)

        # Act
        response = client.get(
            "/api/v1/bots", params={"last_run_at_after": cutoff.isoformat()}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-002"


class TestListBotsCombinedFilters:
    """Test combining multiple filters."""

    def test_multiple_filters_and_logic(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Multiple filters combine with AND logic."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", kill_switch=False)
        create_bot(db_session, rig_id="rig-001", kill_switch=True)
        create_bot(db_session, rig_id="rig-002", kill_switch=False)
        create_bot(db_session, rig_id="rig-002", kill_switch=True)

        # Act
        response = client.get(
            "/api/v1/bots", params={"rig_id": "rig-001", "kill_switch": True}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-001"
        assert data["items"][0]["kill_switch"] is True


class TestListBotsSorting:
    """Test sorting behavior."""

    def test_sorted_newest_first_by_default(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Bots are sorted by create_at DESC by default."""
        # Arrange
        bot1 = create_bot(db_session, rig_id="rig-001")
        bot2 = create_bot(db_session, rig_id="rig-002")
        bot3 = create_bot(db_session, rig_id="rig-003")

        # Act
        response = client.get("/api/v1/bots")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        # Newest first
        assert data["items"][0]["id"] == bot3.id
        assert data["items"][1]["id"] == bot2.id
        assert data["items"][2]["id"] == bot1.id


# --- Get Single Bot Tests ---


class TestGetBot:
    """Test GET /api/v1/bots/{id}."""

    def test_get_bot_found(self, client: TestClient, db_session: Session) -> None:
        """Get existing bot returns all fields."""
        # Arrange
        run_time = datetime.now(timezone.utc)
        bot = create_bot(
            db_session,
            rig_id="rig-001",
            kill_switch=True,
            last_run_log="Test log",
            last_run_at=run_time,
        )

        # Act
        response = client.get(f"/api/v1/bots/{bot.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == bot.id
        assert data["rig_id"] == "rig-001"
        assert data["kill_switch"] is True
        assert data["last_run_log"] == "Test log"
        assert data["last_run_at"] is not None
        assert "create_at" in data
        assert "last_update_at" in data

    def test_get_bot_not_found(self, client: TestClient) -> None:
        """Get nonexistent bot returns 404 with detail."""
        # Act
        response = client.get("/api/v1/bots/nonexistent123")

        # Assert
        assert response.status_code == 404
        data = response.json()
        # HTTPException wraps detail in "detail" key
        assert data["detail"]["detail"] == "Bot not found"
        assert data["detail"]["id"] == "nonexistent123"

    def test_get_bot_response_has_all_fields(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Bot response includes all expected fields."""
        # Arrange
        bot = create_bot(db_session, rig_id="rig-001")

        # Act
        response = client.get(f"/api/v1/bots/{bot.id}")

        # Assert
        assert response.status_code == 200
        data = response.json()
        expected_fields = {
            "id",
            "rig_id",
            "last_run_at",
            "kill_switch",
            "last_run_log",
            "create_at",
            "last_update_at",
        }
        assert set(data.keys()) == expected_fields


# --- PR Review Fixes Tests ---


class TestLogSearchSqlInjectionPrevention:
    """Test that log_search wildcards are escaped properly."""

    def test_log_search_percent_wildcard_escaped(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Percent sign in log_search is treated literally, not as wildcard."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", last_run_log="100% complete")
        create_bot(db_session, rig_id="rig-002", last_run_log="complete")
        create_bot(db_session, rig_id="rig-003", last_run_log="50% done")

        # Act - search for literal "%"
        response = client.get("/api/v1/bots", params={"log_search": "%"})

        # Assert - should only match logs containing literal "%"
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        rig_ids = {item["rig_id"] for item in data["items"]}
        assert rig_ids == {"rig-001", "rig-003"}

    def test_log_search_underscore_wildcard_escaped(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Underscore in log_search is treated literally, not as single-char wildcard."""
        # Arrange
        create_bot(db_session, rig_id="rig-001", last_run_log="test_case passed")
        create_bot(db_session, rig_id="rig-002", last_run_log="testAcase passed")
        create_bot(db_session, rig_id="rig-003", last_run_log="test case passed")

        # Act - search for literal "_"
        response = client.get("/api/v1/bots", params={"log_search": "test_case"})

        # Assert - should only match the one with literal underscore
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-001"


class TestPaginationEdgeCases:
    """Test pagination edge cases from PR review."""

    def test_per_page_one(self, client: TestClient, db_session: Session) -> None:
        """per_page=1 returns single item per page."""
        # Arrange
        create_bot(db_session, rig_id="rig-001")
        create_bot(db_session, rig_id="rig-002")
        create_bot(db_session, rig_id="rig-003")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 1})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3
        assert data["per_page"] == 1
        assert data["pages"] == 3


class TestDeterministicOrdering:
    """Test that ordering is deterministic with secondary sort key."""

    def test_bots_with_same_create_at_have_deterministic_order(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Bots created at same time are ordered deterministically by id."""
        # Arrange - create bots that may have identical create_at timestamps
        bots = []
        for i in range(5):
            bot = create_bot(db_session, rig_id=f"rig-{i:03d}")
            bots.append(bot)

        # Act - fetch twice
        response1 = client.get("/api/v1/bots")
        response2 = client.get("/api/v1/bots")

        # Assert - order should be identical both times
        assert response1.status_code == 200
        assert response2.status_code == 200
        ids1 = [item["id"] for item in response1.json()["items"]]
        ids2 = [item["id"] for item in response2.json()["items"]]
        assert ids1 == ids2
