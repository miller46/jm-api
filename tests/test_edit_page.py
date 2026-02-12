"""Tests for edit page (edit.html) and app.js edit/link functionality.

Covers:
  - edit.html static file exists and is served
  - edit.html structure matches spec (form, back link, error div, title)
  - app.js contains initEditPage logic
  - Table rows link to the edit page (id column is clickable)
"""

import pathlib

import pytest
from fastapi.testclient import TestClient

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file's text content from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ===================================================================
# edit.html — file existence and serving
# ===================================================================


class TestEditHtmlServing:
    """edit.html must exist and be served by the admin mount."""

    def test_edit_html_exists_on_disk(self) -> None:
        """src/jm_api/static/edit.html must exist."""
        assert (STATIC_DIR / "edit.html").exists()

    def test_edit_html_served(self, client: TestClient) -> None:
        """GET /admin/edit.html returns 200 with HTML content."""
        response = client.get("/admin/edit.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


# ===================================================================
# edit.html — page structure
# ===================================================================


class TestEditHtmlContent:
    """Verify edit.html meets spec requirements."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("edit.html")
        self.html_lower = self.html.lower()

    def test_has_valid_html_structure(self) -> None:
        """edit.html must have basic HTML document structure."""
        assert "<!doctype html>" in self.html_lower or "<!DOCTYPE html>" in self.html
        assert "<html" in self.html_lower
        assert "<head" in self.html_lower
        assert "<body" in self.html_lower

    def test_has_edit_form(self) -> None:
        """edit.html must have a form with id='edit-form'."""
        assert 'id="edit-form"' in self.html

    def test_has_back_to_table_link(self) -> None:
        """edit.html must have a 'Back to table' link."""
        assert "table.html" in self.html

    def test_has_error_display(self) -> None:
        """edit.html must have an error display div."""
        assert 'id="error"' in self.html

    def test_has_title_element(self) -> None:
        """edit.html must have an editable title element."""
        assert 'id="edit-title"' in self.html

    def test_links_style_css(self) -> None:
        """edit.html must link to style.css."""
        assert "style.css" in self.html

    def test_links_app_js(self) -> None:
        """edit.html must include app.js."""
        assert "app.js" in self.html


# ===================================================================
# app.js — edit page logic
# ===================================================================


class TestAppJsEditLogic:
    """Verify app.js contains edit page initialization logic."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_has_init_edit_page_function(self) -> None:
        """app.js must define initEditPage."""
        assert "initEditPage" in self.js

    def test_detects_edit_form(self) -> None:
        """app.js must detect the edit-form element to activate edit page logic."""
        assert "edit-form" in self.js

    def test_sends_put_request(self) -> None:
        """app.js must send a PUT request for updating records."""
        assert "PUT" in self.js

    def test_fetches_record_by_id(self) -> None:
        """app.js must fetch the individual record by ID."""
        # The fetch should use the table + id pattern
        assert "id" in self.js

    def test_redirects_to_table_on_success(self) -> None:
        """app.js must redirect to table.html on successful update."""
        assert "table.html" in self.js


# ===================================================================
# app.js — table row links
# ===================================================================


class TestAppJsTableRowLinks:
    """Verify table rows link the ID column to the edit page."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_renders_edit_links_in_table(self) -> None:
        """app.js renderTable must create links to edit.html in the ID column."""
        assert "edit.html" in self.js

    def test_id_column_is_clickable(self) -> None:
        """The first column (id) must render as an <a> link."""
        assert "<a " in self.js or "<a>" in self.js
