"""Tests for Bot read API endpoints."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient


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
        self, client: TestClient, bot_factory
    ) -> None:
        """Page 1 of 25 bots returns 20 items with correct metadata."""
        # Arrange
        for i in range(25):
            bot_factory(rig_id=f"rig-{i:03d}")

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
        self, client: TestClient, bot_factory
    ) -> None:
        """Page 2 of 25 bots returns remaining 5 items."""
        # Arrange
        for i in range(25):
            bot_factory(rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"page": 2})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["total"] == 25
        assert data["page"] == 2
        assert data["pages"] == 2

    def test_list_bots_per_page_over_max_rejected(
        self, client: TestClient
    ) -> None:
        """per_page exceeding 100 returns 422 validation error."""
        # Act
        response = client.get("/api/v1/bots", params={"per_page": 101})

        # Assert - reject with 422, don't silently cap
        assert response.status_code == 422

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
        self, client: TestClient, bot_factory
    ) -> None:
        """40 bots with per_page=20 gives pages=2."""
        # Arrange
        for i in range(40):
            bot_factory(rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 40
        assert data["pages"] == 2

    def test_pagination_pages_with_remainder(
        self, client: TestClient, bot_factory
    ) -> None:
        """41 bots with per_page=20 gives pages=3."""
        # Arrange
        for i in range(41):
            bot_factory(rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 41
        assert data["pages"] == 3

    def test_pagination_single_page(
        self, client: TestClient, bot_factory
    ) -> None:
        """10 bots with per_page=20 gives pages=1."""
        # Arrange
        for i in range(10):
            bot_factory(rig_id=f"rig-{i:03d}")

        # Act
        response = client.get("/api/v1/bots", params={"per_page": 20})

        # Assert
        data = response.json()
        assert data["total"] == 10
        assert data["pages"] == 1

    def test_page_beyond_last_page_returns_empty(
        self, client: TestClient, bot_factory
    ) -> None:
        """Requesting page beyond total pages returns empty items with correct metadata."""
        # Arrange
        for i in range(3):
            bot_factory(rig_id=f"rig-{i:03d}")

        # Act - request page 999 when there's only 1 page
        response = client.get("/api/v1/bots", params={"page": 999, "per_page": 20})

        # Assert - returns empty items but preserves total/pages info
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3
        assert data["page"] == 999
        assert data["pages"] == 1


class TestListBotsFilters:
    """Test filtering functionality."""

    def test_filter_by_rig_id(self, client: TestClient, bot_factory) -> None:
        """Filter by rig_id returns only matching bots."""
        # Arrange
        bot_factory(rig_id="rig-001")
        bot_factory(rig_id="rig-002")
        bot_factory(rig_id="rig-001")

        # Act
        response = client.get("/api/v1/bots", params={"rig_id": "rig-001"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["rig_id"] == "rig-001" for item in data["items"])

    def test_filter_by_kill_switch_true(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by kill_switch=true returns only killed bots."""
        # Arrange
        bot_factory(rig_id="rig-001", kill_switch=True)
        bot_factory(rig_id="rig-002", kill_switch=False)
        bot_factory(rig_id="rig-003", kill_switch=True)

        # Act
        response = client.get("/api/v1/bots", params={"kill_switch": True})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["kill_switch"] is True for item in data["items"])

    def test_filter_by_kill_switch_false(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by kill_switch=false returns only active bots."""
        # Arrange
        bot_factory(rig_id="rig-001", kill_switch=True)
        bot_factory(rig_id="rig-002", kill_switch=False)
        bot_factory(rig_id="rig-003", kill_switch=False)

        # Act
        response = client.get("/api/v1/bots", params={"kill_switch": False})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert all(item["kill_switch"] is False for item in data["items"])

    def test_filter_by_log_search_case_insensitive(
        self, client: TestClient, bot_factory
    ) -> None:
        """log_search matches case-insensitively."""
        # Arrange
        bot_factory(rig_id="rig-001", last_run_log="ERROR occurred")
        bot_factory(rig_id="rig-002", last_run_log="error found")
        bot_factory(rig_id="rig-003", last_run_log="Success")

        # Act
        response = client.get("/api/v1/bots", params={"log_search": "ERROR"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_filter_by_log_search_substring(
        self, client: TestClient, bot_factory
    ) -> None:
        """log_search matches substrings."""
        # Arrange
        bot_factory(rig_id="rig-001", last_run_log="Task failed")
        bot_factory(rig_id="rig-002", last_run_log="failure detected")
        bot_factory(rig_id="rig-003", last_run_log="Success")

        # Act
        response = client.get("/api/v1/bots", params={"log_search": "fail"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    def test_filter_no_results_returns_empty(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter with no matches returns 200 with empty items."""
        # Arrange
        bot_factory(rig_id="rig-001")

        # Act
        response = client.get("/api/v1/bots", params={"rig_id": "nonexistent"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestListBotsDateFilters:
    """Test date range filtering with explicit timestamps."""

    def test_filter_create_at_after(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by create_at_after excludes bots created before cutoff."""
        # Arrange - use explicit timestamps for deterministic testing
        old_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        new_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

        bot_factory(rig_id="rig-old", create_at=old_time)
        bot_factory(rig_id="rig-new", create_at=new_time)

        # Act
        response = client.get(
            "/api/v1/bots", params={"create_at_after": cutoff.isoformat()}
        )

        # Assert - only new bot should be included
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-new"

    def test_filter_create_at_before(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by create_at_before excludes bots created after cutoff."""
        # Arrange - use explicit timestamps
        old_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        new_time = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

        bot_factory(rig_id="rig-old", create_at=old_time)
        bot_factory(rig_id="rig-new", create_at=new_time)

        # Act
        response = client.get(
            "/api/v1/bots", params={"create_at_before": cutoff.isoformat()}
        )

        # Assert - only old bot should be included
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-old"

    def test_filter_create_at_range(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by create_at range includes only bots within range."""
        # Arrange - three bots with distinct timestamps
        early = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        middle = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        late = datetime(2024, 12, 1, 12, 0, 0, tzinfo=timezone.utc)

        bot_factory(rig_id="rig-early", create_at=early)
        bot_factory(rig_id="rig-middle", create_at=middle)
        bot_factory(rig_id="rig-late", create_at=late)

        # Act - filter for middle range
        range_start = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        range_end = datetime(2024, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
        response = client.get(
            "/api/v1/bots",
            params={
                "create_at_after": range_start.isoformat(),
                "create_at_before": range_end.isoformat(),
            },
        )

        # Assert - only middle bot should be included
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-middle"

    def test_filter_last_run_at_after(
        self, client: TestClient, bot_factory
    ) -> None:
        """Filter by last_run_at_after returns only bots that ran after cutoff."""
        # Arrange
        past = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        recent = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        cutoff = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)

        bot_factory(rig_id="rig-old-run", last_run_at=past)
        bot_factory(rig_id="rig-new-run", last_run_at=recent)
        bot_factory(rig_id="rig-no-run", last_run_at=None)

        # Act
        response = client.get(
            "/api/v1/bots", params={"last_run_at_after": cutoff.isoformat()}
        )

        # Assert - only recent run bot should be included
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-new-run"


class TestListBotsCombinedFilters:
    """Test combining multiple filters."""

    def test_multiple_filters_and_logic(
        self, client: TestClient, bot_factory
    ) -> None:
        """Multiple filters combine with AND logic."""
        # Arrange
        bot_factory(rig_id="rig-001", kill_switch=False)
        bot_factory(rig_id="rig-001", kill_switch=True)
        bot_factory(rig_id="rig-002", kill_switch=False)
        bot_factory(rig_id="rig-002", kill_switch=True)

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
        self, client: TestClient, bot_factory
    ) -> None:
        """Bots are sorted by create_at DESC by default."""
        # Arrange
        bot1 = bot_factory(rig_id="rig-001")
        bot2 = bot_factory(rig_id="rig-002")
        bot3 = bot_factory(rig_id="rig-003")

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

    def test_get_bot_found(self, client: TestClient, bot_factory) -> None:
        """Get existing bot returns all fields."""
        # Arrange
        run_time = datetime.now(timezone.utc)
        bot = bot_factory(
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
        """Get nonexistent bot returns 404 with flat detail structure."""
        # Act - use valid 32-char alphanumeric ID format
        nonexistent_id = "aaaabbbbccccddddeeeeffffgggghhhh"
        response = client.get(f"/api/v1/bots/{nonexistent_id}")

        # Assert
        assert response.status_code == 404
        data = response.json()
        # Flat structure under "detail" key (not double-nested)
        assert data["detail"]["message"] == "Bot not found"
        assert data["detail"]["id"] == nonexistent_id

    def test_get_bot_response_has_all_fields(
        self, client: TestClient, bot_factory
    ) -> None:
        """Bot response includes all expected fields."""
        # Arrange
        bot = bot_factory(rig_id="rig-001")

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
        self, client: TestClient, bot_factory
    ) -> None:
        """Percent sign in log_search is treated literally, not as wildcard."""
        # Arrange
        bot_factory(rig_id="rig-001", last_run_log="100% complete")
        bot_factory(rig_id="rig-002", last_run_log="complete")
        bot_factory(rig_id="rig-003", last_run_log="50% done")

        # Act - search for literal "%"
        response = client.get("/api/v1/bots", params={"log_search": "%"})

        # Assert - should only match logs containing literal "%"
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        rig_ids = {item["rig_id"] for item in data["items"]}
        assert rig_ids == {"rig-001", "rig-003"}

    def test_log_search_underscore_wildcard_escaped(
        self, client: TestClient, bot_factory
    ) -> None:
        """Underscore in log_search is treated literally, not as single-char wildcard."""
        # Arrange
        bot_factory(rig_id="rig-001", last_run_log="test_case passed")
        bot_factory(rig_id="rig-002", last_run_log="testAcase passed")
        bot_factory(rig_id="rig-003", last_run_log="test case passed")

        # Act - search for literal "_"
        response = client.get("/api/v1/bots", params={"log_search": "test_case"})

        # Assert - should only match the one with literal underscore
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["rig_id"] == "rig-001"


class TestPaginationEdgeCases:
    """Test pagination edge cases from PR review."""

    def test_per_page_one(self, client: TestClient, bot_factory) -> None:
        """per_page=1 returns single item per page."""
        # Arrange
        bot_factory(rig_id="rig-001")
        bot_factory(rig_id="rig-002")
        bot_factory(rig_id="rig-003")

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
        self, client: TestClient, bot_factory
    ) -> None:
        """Bots created at same time are ordered deterministically by id."""
        # Arrange - create bots that may have identical create_at timestamps
        bots = []
        for i in range(5):
            bot = bot_factory(rig_id=f"rig-{i:03d}")
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


class TestBotIdValidation:
    """Test bot_id path parameter validation."""

    def test_get_bot_invalid_id_too_short(self, client: TestClient) -> None:
        """bot_id shorter than 32 characters returns 422."""
        # Act
        response = client.get("/api/v1/bots/abc123")

        # Assert
        assert response.status_code == 422

    def test_get_bot_invalid_id_too_long(self, client: TestClient) -> None:
        """bot_id longer than 32 characters returns 422."""
        # Act - 33 character ID
        long_id = "a" * 33
        response = client.get(f"/api/v1/bots/{long_id}")

        # Assert
        assert response.status_code == 422

    def test_get_bot_invalid_id_non_alphanumeric(self, client: TestClient) -> None:
        """bot_id with non-alphanumeric characters returns 422."""
        # Act - ID with special characters
        response = client.get("/api/v1/bots/abc-123-def-456-ghi-789-jkl-012")

        # Assert
        assert response.status_code == 422

    def test_get_bot_valid_id_format_not_found(self, client: TestClient) -> None:
        """Valid 32-char alphanumeric bot_id that doesn't exist returns 404."""
        # Act - valid format but bot doesn't exist
        response = client.get("/api/v1/bots/a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6")

        # Assert - should be 404 not found, not 422 validation error
        assert response.status_code == 404
