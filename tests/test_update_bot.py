"""Tests for Bot update (PUT) API endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestUpdateBotSuccess:
    """Test PUT /api/v1/bots/{id} updates a record."""

    def test_update_bot_returns_200(self, client: TestClient, bot_factory) -> None:
        """Successful update returns 200."""
        bot = bot_factory(rig_id="rig-update")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"rig_id": "rig-updated"}
        )
        assert response.status_code == 200

    def test_update_bot_changes_field(self, client: TestClient, bot_factory) -> None:
        """Updated field is reflected in the response."""
        bot = bot_factory(rig_id="rig-old")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"rig_id": "rig-new"}
        )
        assert response.json()["rig_id"] == "rig-new"

    def test_partial_update_preserves_other_fields(
        self, client: TestClient, bot_factory
    ) -> None:
        """Partial update only changes provided fields."""
        bot = bot_factory(rig_id="rig-keep", kill_switch=False)
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"kill_switch": True}
        )
        data = response.json()
        assert data["kill_switch"] is True
        assert data["rig_id"] == "rig-keep"

    def test_update_persists_via_get(self, client: TestClient, bot_factory) -> None:
        """Updated values persist when re-fetched."""
        bot = bot_factory(rig_id="rig-persist")
        client.put(f"/api/v1/bots/{bot.id}", json={"rig_id": "rig-persisted"})
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.json()["rig_id"] == "rig-persisted"

    def test_update_returns_all_fields(self, client: TestClient, bot_factory) -> None:
        """PUT response includes all BotResponse fields."""
        bot = bot_factory(rig_id="rig-fields")
        response = client.put(
            f"/api/v1/bots/{bot.id}", json={"rig_id": "rig-fields-2"}
        )
        expected = {
            "id", "rig_id", "last_run_at", "kill_switch",
            "last_run_log", "create_at", "last_update_at",
        }
        assert set(response.json().keys()) == expected


class TestUpdateBotNotFound:
    """Test PUT /api/v1/bots/{id} with nonexistent ID."""

    def test_nonexistent_bot_returns_404(self, client: TestClient) -> None:
        """PUT to nonexistent bot ID returns 404."""
        fake_id = "x" * 32
        response = client.put(
            f"/api/v1/bots/{fake_id}", json={"rig_id": "nope"}
        )
        assert response.status_code == 404
