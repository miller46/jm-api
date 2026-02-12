"""Integration tests for edit page behavior — replaces low-value string-matching tests.

Covers:
  - Issue 3: XSS fix verification — renderEditForm uses safe DOM APIs
  - Issue 4: Real integration tests — create → update → verify round-trip
  - Structural tests for edit.html (keeping the valid ones)
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ===================================================================
# Issue 3: XSS fix — renderEditForm must use safe DOM APIs
# ===================================================================


class TestRenderEditFormXssSafety:
    """renderEditForm must use DOM APIs instead of string interpolation."""

    def test_render_edit_form_uses_create_element(self) -> None:
        """renderEditForm must use document.createElement for safe DOM construction."""
        js = _read_static("app.js")
        # Extract the renderEditForm function body
        start = js.index("function renderEditForm")
        # Find the next top-level function (starts at column 0)
        next_fn = js.index("\nfunction ", start + 1)
        edit_form_body = js[start:next_fn]
        assert "createElement" in edit_form_body, (
            "renderEditForm should use document.createElement for XSS safety"
        )

    def test_render_edit_form_uses_set_attribute(self) -> None:
        """renderEditForm must use setAttribute for setting input values safely."""
        js = _read_static("app.js")
        start = js.index("function renderEditForm")
        next_fn = js.index("\nfunction ", start + 1)
        edit_form_body = js[start:next_fn]
        # Should use setAttribute or .value = for safe value assignment
        assert "setAttribute" in edit_form_body or ".value" in edit_form_body, (
            "renderEditForm should use setAttribute or .value for safe value setting"
        )

    def test_render_edit_form_no_inner_html_with_values(self) -> None:
        """renderEditForm must not use innerHTML with record values (XSS risk)."""
        js = _read_static("app.js")
        start = js.index("function renderEditForm")
        next_fn = js.index("\nfunction ", start + 1)
        edit_form_body = js[start:next_fn]
        # Should not have the pattern: value="' + displayVal + '"
        assert 'value="' not in edit_form_body, (
            "renderEditForm should not interpolate values into HTML attribute strings"
        )


# ===================================================================
# Issue 4: Real integration tests — API round-trip
# ===================================================================


class TestEditRoundTrip:
    """Integration tests: create → update → verify via GET."""

    def test_create_then_update_then_verify(
        self, client: TestClient, bot_factory
    ) -> None:
        """Full round-trip: create bot, update via PUT, verify via GET."""
        bot = bot_factory(rig_id="rig-roundtrip", kill_switch=False)

        # Update
        put_resp = client.put(
            f"/api/v1/bots/{bot.id}",
            json={"rig_id": "rig-updated", "kill_switch": True},
        )
        assert put_resp.status_code == 200
        put_data = put_resp.json()
        assert put_data["rig_id"] == "rig-updated"
        assert put_data["kill_switch"] is True

        # Verify via GET
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["rig_id"] == "rig-updated"
        assert get_data["kill_switch"] is True

    def test_partial_update_preserves_other_fields(
        self, client: TestClient, bot_factory
    ) -> None:
        """Partial update: only change one field, verify others unchanged."""
        bot = bot_factory(
            rig_id="rig-partial", kill_switch=False, last_run_log="original log"
        )

        # Update only rig_id
        put_resp = client.put(
            f"/api/v1/bots/{bot.id}", json={"rig_id": "rig-new"}
        )
        assert put_resp.status_code == 200

        # Verify other fields untouched
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        data = get_resp.json()
        assert data["rig_id"] == "rig-new"
        assert data["kill_switch"] is False
        assert data["last_run_log"] == "original log"

    def test_update_nonexistent_returns_404(self, client: TestClient) -> None:
        """PUT to nonexistent bot returns 404 with proper error body."""
        fake_id = "z" * 32
        resp = client.put(
            f"/api/v1/bots/{fake_id}", json={"rig_id": "nope"}
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
        assert data["detail"]["message"] == "Bot not found"

    def test_empty_update_is_noop(
        self, client: TestClient, bot_factory
    ) -> None:
        """PUT with empty body changes nothing."""
        bot = bot_factory(rig_id="rig-noop", kill_switch=False)
        put_resp = client.put(f"/api/v1/bots/{bot.id}", json={})
        assert put_resp.status_code == 200
        assert put_resp.json()["rig_id"] == "rig-noop"

    def test_update_nullable_field_to_null(
        self, client: TestClient, bot_factory
    ) -> None:
        """Setting nullable field to null succeeds."""
        bot = bot_factory(rig_id="rig-null", last_run_log="has log")
        put_resp = client.put(
            f"/api/v1/bots/{bot.id}", json={"last_run_log": None}
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["last_run_log"] is None

        # Verify persisted
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.json()["last_run_log"] is None

    def test_edit_page_served(self, client: TestClient) -> None:
        """GET /admin/edit.html returns 200 with HTML."""
        resp = client.get("/admin/edit.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
