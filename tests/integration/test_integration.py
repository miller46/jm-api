"""Integration tests — real HTTP requests against a live uvicorn server."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.orm import Session

from jm_api.models.bot import Bot

# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


class TestHealthEndpoint:
    """Tests for GET /api/v1/healthz."""

    def test_healthz_returns_200_with_ok_body(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/api/v1/healthz")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_healthz_includes_x_request_id_header(self, http_client: httpx.Client) -> None:
        resp = http_client.get("/api/v1/healthz")

        assert resp.status_code == 200
        request_id = resp.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) > 0


# ---------------------------------------------------------------------------
# Bot endpoint tests
# ---------------------------------------------------------------------------


class TestBotListEndpoint:
    """Tests for GET /api/v1/bots.

    Each test is fully self-contained.  The autouse ``_clean_bots_table``
    fixture in conftest truncates the bots table *before* every test
    ("clean before" pattern), so no manual cleanup is needed and teardown
    ordering with ``db_session`` is irrelevant.
    """

    def test_list_bots_empty_db(self, http_client: httpx.Client) -> None:
        """An empty bots table returns total=0 and no items."""
        resp = http_client.get("/api/v1/bots")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_bots_returns_inserted_bot(
        self, http_client: httpx.Client, db_session: Session
    ) -> None:
        bot = Bot(rig_id="test-rig")
        db_session.add(bot)
        db_session.commit()
        db_session.refresh(bot)

        resp = http_client.get("/api/v1/bots")

        assert resp.status_code == 200
        body = resp.json()
        items = body["items"]
        assert any(item["rig_id"] == "test-rig" for item in items)

    def test_filter_bots_by_rig_id(
        self, http_client: httpx.Client, db_session: Session
    ) -> None:
        bot1 = Bot(rig_id="test-rig-1")
        bot2 = Bot(rig_id="test-rig-2")
        db_session.add_all([bot1, bot2])
        db_session.commit()

        resp = http_client.get("/api/v1/bots", params={"rig_id": "test-rig-1"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["rig_id"] == "test-rig-1"

    def test_list_bots_pagination(
        self, http_client: httpx.Client, db_session: Session
    ) -> None:
        bots = [Bot(rig_id=f"pag-rig-{i}") for i in range(3)]
        db_session.add_all(bots)
        db_session.commit()

        resp = http_client.get("/api/v1/bots", params={"page": 1, "per_page": 2})

        assert resp.status_code == 200
        body = resp.json()
        assert body["per_page"] == 2
        assert body["page"] == 1
        assert body["pages"] == 2
        assert body["total"] == 3
        assert len(body["items"]) == 2


class TestCleanBeforePattern:
    """Verify the autouse cleanup fixture uses the 'clean before' pattern.

    Instead of relying on two order-dependent tests (which would break under
    ``pytest-randomly``), a single test inserts a row, then invokes the same
    ``clean_bots_table_fn`` helper that the ``_clean_bots_table`` fixture
    calls, and asserts the table is empty afterward.  This proves the
    fixture's actual code path works correctly.
    """

    def test_clean_before_pattern_removes_leftover_rows(
        self, http_client: httpx.Client, db_session: Session, clean_bots_table_fn
    ) -> None:
        """Insert a bot, run the fixture's cleanup helper, verify table is empty."""
        # Arrange: insert a bot so the table is non-empty
        bot = Bot(rig_id="leftover-rig")
        db_session.add(bot)
        db_session.commit()

        resp = http_client.get("/api/v1/bots")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1, "Precondition: table should have at least one row"

        # Act: call the same helper the _clean_bots_table fixture uses
        clean_bots_table_fn()

        # Assert: table is now empty — proves the fixture's cleanup logic works
        resp = http_client.get("/api/v1/bots")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0, (
            "Expected empty table after clean; "
            "clean_bots_table_fn() did not remove leftover rows"
        )
        assert body["items"] == []

    def test_clean_before_pattern_is_idempotent(
        self, http_client: httpx.Client, clean_bots_table_fn
    ) -> None:
        """Calling the cleanup helper on an already-empty table is safe."""
        # Act: call cleanup on an already-clean table (autouse fixture already ran)
        clean_bots_table_fn()

        # Assert: table is still empty — no error from cleaning an empty table
        resp = http_client.get("/api/v1/bots")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []


class TestBotDetailEndpoint:
    """Tests for GET /api/v1/bots/{id}."""

    def test_get_bot_by_id(
        self, http_client: httpx.Client, db_session: Session
    ) -> None:
        bot = Bot(rig_id="detail-rig")
        db_session.add(bot)
        db_session.commit()
        db_session.refresh(bot)

        resp = http_client.get(f"/api/v1/bots/{bot.id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == bot.id
        assert body["rig_id"] == "detail-rig"

    def test_get_bot_nonexistent_returns_404(self, http_client: httpx.Client) -> None:
        # ID must be 32 alphanumeric chars to pass path validation
        resp = http_client.get("/api/v1/bots/nonexistentidabc0000000000000000")

        assert resp.status_code == 404
