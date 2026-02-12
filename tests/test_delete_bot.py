"""Tests for Bot delete (DELETE) API endpoint.

Covers spec acceptance criteria:
- DELETE /api/v1/bots/{id} returns 204 and removes the record
- DELETE /api/v1/bots/{invalid_id} returns 404
- Error response displayed if delete fails
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient


class TestDeleteBotSuccess:
    """Test DELETE /api/v1/bots/{id} removes a record."""

    def test_delete_bot_returns_204(self, client: TestClient, bot_factory) -> None:
        """Successful delete returns 204 No Content."""
        bot = bot_factory(rig_id="rig-delete")
        response = client.delete(f"/api/v1/bots/{bot.id}")
        assert response.status_code == 204

    def test_delete_bot_returns_empty_body(self, client: TestClient, bot_factory) -> None:
        """Successful delete response has no body."""
        bot = bot_factory(rig_id="rig-empty-body")
        response = client.delete(f"/api/v1/bots/{bot.id}")
        assert response.content == b""

    def test_deleted_bot_not_found_on_get(self, client: TestClient, bot_factory) -> None:
        """Deleted bot returns 404 when fetched via GET."""
        bot = bot_factory(rig_id="rig-gone")
        client.delete(f"/api/v1/bots/{bot.id}")
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.status_code == 404

    def test_deleted_bot_excluded_from_list(self, client: TestClient, bot_factory) -> None:
        """Deleted bot does not appear in list endpoint results."""
        bot1 = bot_factory(rig_id="rig-keep")
        bot2 = bot_factory(rig_id="rig-remove")
        client.delete(f"/api/v1/bots/{bot2.id}")

        list_resp = client.get("/api/v1/bots")
        items = list_resp.json()["items"]
        ids = [item["id"] for item in items]
        assert bot1.id in ids
        assert bot2.id not in ids

    def test_delete_one_bot_does_not_affect_others(
        self, client: TestClient, bot_factory
    ) -> None:
        """Deleting one bot leaves other bots intact."""
        bot_keep = bot_factory(rig_id="rig-survivor")
        bot_delete = bot_factory(rig_id="rig-doomed")
        client.delete(f"/api/v1/bots/{bot_delete.id}")

        get_resp = client.get(f"/api/v1/bots/{bot_keep.id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["rig_id"] == "rig-survivor"

    def test_list_total_decremented_after_delete(
        self, client: TestClient, bot_factory
    ) -> None:
        """Total count in list response decreases by 1 after deletion."""
        bot_factory(rig_id="rig-count-1")
        bot2 = bot_factory(rig_id="rig-count-2")

        before = client.get("/api/v1/bots").json()["total"]
        client.delete(f"/api/v1/bots/{bot2.id}")
        after = client.get("/api/v1/bots").json()["total"]

        assert after == before - 1

    def test_delete_bot_with_all_fields_populated(
        self, client: TestClient, bot_factory
    ) -> None:
        """Bot with all fields set (including optional) can be deleted."""
        bot = bot_factory(
            rig_id="rig-full",
            kill_switch=True,
            last_run_log="Complete run log entry",
            last_run_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        )
        response = client.delete(f"/api/v1/bots/{bot.id}")
        assert response.status_code == 204

        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.status_code == 404


class TestDeleteBotNotFound:
    """Test DELETE /api/v1/bots/{id} with nonexistent ID."""

    def test_nonexistent_bot_returns_404(self, client: TestClient) -> None:
        """DELETE of nonexistent bot ID returns 404."""
        fake_id = "x" * 32
        response = client.delete(f"/api/v1/bots/{fake_id}")
        assert response.status_code == 404

    def test_404_response_contains_message(self, client: TestClient) -> None:
        """404 response includes human-readable message with model name."""
        fake_id = "a" * 32
        response = client.delete(f"/api/v1/bots/{fake_id}")
        data = response.json()
        assert data["detail"]["message"] == "Bot not found"

    def test_404_response_contains_id(self, client: TestClient) -> None:
        """404 response includes the requested ID."""
        fake_id = "b" * 32
        response = client.delete(f"/api/v1/bots/{fake_id}")
        data = response.json()
        assert data["detail"]["id"] == fake_id

    def test_404_detail_has_correct_structure(self, client: TestClient) -> None:
        """404 detail contains exactly message and id keys."""
        fake_id = "c" * 32
        response = client.delete(f"/api/v1/bots/{fake_id}")
        detail = response.json()["detail"]
        assert isinstance(detail, dict)
        assert set(detail.keys()) == {"message", "id"}

    def test_404_response_is_json(self, client: TestClient) -> None:
        """404 error response has application/json content type."""
        fake_id = "d" * 32
        response = client.delete(f"/api/v1/bots/{fake_id}")
        assert "application/json" in response.headers.get("content-type", "")


class TestDeleteBotIdempotency:
    """Test that deleting the same record twice behaves correctly."""

    def test_second_delete_returns_404(self, client: TestClient, bot_factory) -> None:
        """Deleting an already-deleted record returns 404."""
        bot = bot_factory(rig_id="rig-twice")
        first = client.delete(f"/api/v1/bots/{bot.id}")
        assert first.status_code == 204

        second = client.delete(f"/api/v1/bots/{bot.id}")
        assert second.status_code == 404

    def test_second_delete_404_has_correct_message(
        self, client: TestClient, bot_factory
    ) -> None:
        """Second delete of same record includes proper 404 error body."""
        bot = bot_factory(rig_id="rig-twice-msg")
        client.delete(f"/api/v1/bots/{bot.id}")

        second = client.delete(f"/api/v1/bots/{bot.id}")
        data = second.json()
        assert data["detail"]["message"] == "Bot not found"
        assert data["detail"]["id"] == bot.id


class TestDeleteBotIdValidation:
    """Test path parameter validation on DELETE endpoint."""

    def test_short_id_returns_422(self, client: TestClient) -> None:
        """ID shorter than 32 characters is rejected."""
        response = client.delete("/api/v1/bots/abc")
        assert response.status_code == 422

    def test_long_id_returns_422(self, client: TestClient) -> None:
        """ID longer than 32 characters is rejected."""
        long_id = "a" * 33
        response = client.delete(f"/api/v1/bots/{long_id}")
        assert response.status_code == 422

    def test_special_chars_in_id_returns_422(self, client: TestClient) -> None:
        """ID with special characters is rejected."""
        bad_id = "abc!@#$%^&*()_+{}|:<>?-=[]\\;',./"
        response = client.delete(f"/api/v1/bots/{bad_id}")
        assert response.status_code == 422

    def test_id_with_spaces_returns_422(self, client: TestClient) -> None:
        """ID containing spaces is rejected."""
        response = client.delete("/api/v1/bots/abcdefghijklmnop qrstuvwxyz12345")
        assert response.status_code == 422

    def test_valid_format_id_accepted(self, client: TestClient) -> None:
        """32-char alphanumeric ID passes validation (returns 404, not 422)."""
        valid_id = "abcdefghijklmnopqrstuvwxyz123456"
        response = client.delete(f"/api/v1/bots/{valid_id}")
        # 404 because record doesn't exist, but NOT 422 — validation passed
        assert response.status_code == 404

    def test_uppercase_id_passes_validation(self, client: TestClient) -> None:
        """32-char uppercase alphanumeric ID passes regex validation."""
        upper_id = "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        response = client.delete(f"/api/v1/bots/{upper_id}")
        assert response.status_code == 404

    def test_single_char_id_returns_422(self, client: TestClient) -> None:
        """Single-character ID is rejected."""
        response = client.delete("/api/v1/bots/a")
        assert response.status_code == 422

    def test_sql_injection_in_id_returns_422(self, client: TestClient) -> None:
        """SQL injection attempt in ID is rejected by regex."""
        response = client.delete("/api/v1/bots/1'; DROP TABLE bots;--aaaaaaa")
        assert response.status_code == 422


class TestDeleteBotIntegration:
    """Integration tests: delete interacts correctly with other operations."""

    def test_delete_after_update(self, client: TestClient, bot_factory) -> None:
        """Bot can be deleted after being updated."""
        bot = bot_factory(rig_id="rig-update-then-delete")
        # Update the bot
        client.put(
            f"/api/v1/bots/{bot.id}",
            json={"rig_id": "rig-updated"},
        )
        # Now delete
        response = client.delete(f"/api/v1/bots/{bot.id}")
        assert response.status_code == 204

        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.status_code == 404

    def test_update_after_delete_returns_404(
        self, client: TestClient, bot_factory
    ) -> None:
        """Updating a deleted bot returns 404."""
        bot = bot_factory(rig_id="rig-delete-then-update")
        client.delete(f"/api/v1/bots/{bot.id}")

        response = client.put(
            f"/api/v1/bots/{bot.id}",
            json={"rig_id": "rig-ghost"},
        )
        assert response.status_code == 404

    def test_delete_all_bots_one_by_one(
        self, client: TestClient, bot_factory
    ) -> None:
        """Deleting all bots empties the collection."""
        bots = [bot_factory(rig_id=f"rig-{i}") for i in range(3)]

        for bot in bots:
            resp = client.delete(f"/api/v1/bots/{bot.id}")
            assert resp.status_code == 204

        list_resp = client.get("/api/v1/bots")
        assert list_resp.json()["total"] == 0
        assert list_resp.json()["items"] == []

    def test_create_after_delete(self, client: TestClient, bot_factory) -> None:
        """New bots can be created after deleting existing ones."""
        bot = bot_factory(rig_id="rig-old")
        client.delete(f"/api/v1/bots/{bot.id}")

        new_resp = client.post("/api/v1/bots", json={"rig_id": "rig-new"})
        assert new_resp.status_code == 201
        assert new_resp.json()["rig_id"] == "rig-new"

    def test_filter_excludes_deleted_bot(
        self, client: TestClient, bot_factory
    ) -> None:
        """Deleted bots are excluded from filtered list results."""
        bot1 = bot_factory(rig_id="rig-same")
        bot2 = bot_factory(rig_id="rig-same")
        client.delete(f"/api/v1/bots/{bot1.id}")

        list_resp = client.get("/api/v1/bots", params={"rig_id": "rig-same"})
        data = list_resp.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == bot2.id

    def test_pagination_correct_after_delete(
        self, client: TestClient, bot_factory
    ) -> None:
        """Pagination metadata updates correctly after deletion."""
        bots = [bot_factory(rig_id=f"rig-page-{i}") for i in range(3)]
        client.delete(f"/api/v1/bots/{bots[0].id}")

        list_resp = client.get("/api/v1/bots", params={"per_page": 2})
        data = list_resp.json()
        assert data["total"] == 2
        assert data["pages"] == 1
        assert len(data["items"]) == 2
