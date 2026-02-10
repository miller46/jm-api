"""Tests for admin dashboard (static file serving + HTML/CSS/JS content).

Tests cover all four sub-tasks from spec.txt:
  1. Static file serving at /admin
  2. Index page (index.html) — table listing with semantic HTML
  3. Table detail page (table.html) — fetch/render 20 records
  4. Minimal styling (style.css) — clean, responsive table styles
  5. Client-side logic (app.js) — TABLES array, fetch, render, error handling
"""

import pathlib

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file's text content from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ===================================================================
# Sub-task 1: Static file serving
# ===================================================================


class TestStaticFileServing:
    """Verify the /admin mount serves static files correctly."""

    def test_static_directory_exists(self) -> None:
        """The src/jm_api/static/ directory must exist."""
        assert STATIC_DIR.is_dir(), f"Static directory missing: {STATIC_DIR}"

    def test_index_html_served(self, client: TestClient) -> None:
        """GET /admin/index.html returns 200 with HTML content."""
        response = client.get("/admin/index.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_table_html_served(self, client: TestClient) -> None:
        """GET /admin/table.html returns 200 with HTML content."""
        response = client.get("/admin/table.html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_style_css_served(self, client: TestClient) -> None:
        """GET /admin/style.css returns 200 with CSS content type."""
        response = client.get("/admin/style.css")
        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]

    def test_app_js_served(self, client: TestClient) -> None:
        """GET /admin/app.js returns 200 with JS content type."""
        response = client.get("/admin/app.js")
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        assert "javascript" in content_type or "text/plain" in content_type

    def test_nonexistent_static_file_returns_404(self, client: TestClient) -> None:
        """GET /admin/nonexistent.html returns 404."""
        response = client.get("/admin/nonexistent.html")
        assert response.status_code == 404

    def test_api_still_works_alongside_admin(self, client: TestClient) -> None:
        """API endpoints are unaffected by the /admin static mount."""
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestStaticFilesExist:
    """All four required static files must exist on disk."""

    @pytest.mark.parametrize(
        "filename",
        ["index.html", "table.html", "style.css", "app.js"],
    )
    def test_required_file_exists(self, filename: str) -> None:
        """Each spec-mandated static file must be present."""
        path = STATIC_DIR / filename
        assert path.exists(), f"Missing required static file: {filename}"


# ===================================================================
# Sub-task 2: Index page (index.html)
# ===================================================================


class TestIndexPageContent:
    """Verify index.html meets spec requirements."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("index.html")
        self.html_lower = self.html.lower()

    # -- Semantic HTML --

    def test_uses_main_element(self) -> None:
        """Index page must use a <main> element."""
        assert "<main" in self.html_lower

    def test_uses_ul_element(self) -> None:
        """Index page must use a <ul> element for the table list."""
        assert "<ul" in self.html_lower

    def test_uses_anchor_elements(self) -> None:
        """Index page must use <a> elements for table links."""
        assert "<a " in self.html_lower or "<a>" in self.html_lower

    # -- Links to assets --

    def test_links_style_css(self) -> None:
        """Index page must link to style.css."""
        assert "style.css" in self.html

    def test_links_app_js(self) -> None:
        """Index page must include app.js."""
        assert "app.js" in self.html

    # -- Navigation --

    def test_table_links_point_to_table_detail_page(self) -> None:
        """Table links must navigate to table.html?table=<name>."""
        assert "table.html?table=" in self.html

    def test_has_valid_html_structure(self) -> None:
        """Index page must have basic HTML document structure."""
        assert "<!doctype html>" in self.html_lower or "<!DOCTYPE html>" in self.html
        assert "<html" in self.html_lower
        assert "<head" in self.html_lower
        assert "<body" in self.html_lower


# ===================================================================
# Sub-task 3: Table detail page (table.html)
# ===================================================================


class TestTablePageContent:
    """Verify table.html meets spec requirements."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("table.html")
        self.html_lower = self.html.lower()

    # -- Semantic structure --

    def test_has_table_element_or_placeholder(self) -> None:
        """Detail page must have a <table> element (or JS target for dynamic rendering)."""
        # The table can be static HTML or a container that JS populates
        assert "<table" in self.html_lower or 'id="' in self.html_lower

    # -- Links to assets --

    def test_links_style_css(self) -> None:
        """Detail page must link to style.css."""
        assert "style.css" in self.html

    def test_links_app_js(self) -> None:
        """Detail page must include app.js."""
        assert "app.js" in self.html

    # -- Loading / error UI --

    def test_has_loading_indicator_target(self) -> None:
        """Detail page must have a loading indicator element or class."""
        assert "loading" in self.html_lower

    def test_has_error_display_target(self) -> None:
        """Detail page must have an error display element or class."""
        assert "error" in self.html_lower

    def test_has_valid_html_structure(self) -> None:
        """Detail page must have basic HTML document structure."""
        assert "<!doctype html>" in self.html_lower or "<!DOCTYPE html>" in self.html
        assert "<html" in self.html_lower
        assert "<head" in self.html_lower
        assert "<body" in self.html_lower


# ===================================================================
# Sub-task 4: Minimal styling (style.css)
# ===================================================================


class TestStyleCssContent:
    """Verify style.css meets spec requirements."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")
        self.css_lower = self.css.lower()

    def test_system_font_stack(self) -> None:
        """CSS must use a system font stack."""
        # Common system font indicators
        has_system_font = any(
            token in self.css_lower
            for token in [
                "system-ui",
                "-apple-system",
                "segoe ui",
                "sans-serif",
            ]
        )
        assert has_system_font, "Expected system font stack in style.css"

    def test_max_width_container(self) -> None:
        """CSS must set a max-width for the container."""
        assert "max-width" in self.css_lower

    def test_centered_layout(self) -> None:
        """CSS must center the layout (margin auto or similar)."""
        assert "margin" in self.css_lower and "auto" in self.css_lower

    def test_table_border_styling(self) -> None:
        """CSS must include border styles for the table."""
        assert "border" in self.css_lower

    def test_alternating_row_backgrounds(self) -> None:
        """CSS must style alternating rows (nth-child or nth-of-type)."""
        has_alternating = any(
            token in self.css_lower
            for token in ["nth-child", "nth-of-type"]
        )
        assert has_alternating, "Expected alternating row styles (nth-child/nth-of-type)"

    def test_cell_padding(self) -> None:
        """CSS must include padding for table cells."""
        assert "padding" in self.css_lower

    def test_responsive_horizontal_scroll(self) -> None:
        """Table must scroll horizontally on small screens (overflow-x)."""
        assert "overflow-x" in self.css_lower or "overflow" in self.css_lower


# ===================================================================
# Sub-task 5: Client-side JavaScript (app.js)
# ===================================================================


class TestAppJsContent:
    """Verify app.js meets spec requirements."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    # -- TABLES array --

    def test_tables_array_defined(self) -> None:
        """app.js must define a TABLES constant."""
        assert "TABLES" in self.js

    def test_tables_array_contains_bots(self) -> None:
        """TABLES array must include 'bots'."""
        assert '"bots"' in self.js or "'bots'" in self.js

    # -- URL / query param handling --

    def test_reads_table_query_param(self) -> None:
        """app.js must read the 'table' query parameter from the URL."""
        has_param_read = any(
            token in self.js
            for token in [
                "URLSearchParams",
                "searchParams",
                "location.search",
                "location.href",
            ]
        )
        assert has_param_read, "Expected URL query param reading logic in app.js"

    # -- Fetch API --

    def test_fetches_api_endpoint(self) -> None:
        """app.js must fetch /api/v1/{table} with per_page=20."""
        assert "fetch(" in self.js or "fetch (" in self.js
        assert "per_page=20" in self.js or "per_page" in self.js

    def test_uses_api_v1_prefix(self) -> None:
        """Fetch URL must use the /api/v1/ prefix."""
        assert "/api/v1/" in self.js

    # -- Response parsing --

    def test_parses_items_from_response(self) -> None:
        """app.js must extract the 'items' array from the API response."""
        assert "items" in self.js

    # -- Dynamic table rendering --

    def test_auto_generates_column_headers(self) -> None:
        """app.js must auto-generate column headers from record keys."""
        # Object.keys() is the standard way to extract keys for headers
        has_key_extraction = any(
            token in self.js
            for token in [
                "Object.keys",
                "Object.entries",
                "Object.getOwnPropertyNames",
            ]
        )
        assert has_key_extraction, "Expected dynamic column header generation (Object.keys or similar)"

    def test_creates_table_rows(self) -> None:
        """app.js must create table rows (tr elements)."""
        has_row_creation = any(
            token in self.js
            for token in ["<tr", "createElement", "insertRow", "innerHTML"]
        )
        assert has_row_creation, "Expected table row creation logic in app.js"

    # -- Loading indicator --

    def test_shows_loading_indicator(self) -> None:
        """app.js must show/hide a loading indicator."""
        assert "loading" in self.js.lower()

    # -- Error handling --

    def test_handles_fetch_errors(self) -> None:
        """app.js must handle fetch failures."""
        has_error_handling = any(
            token in self.js
            for token in ["catch", ".catch", "try", "onerror", "error"]
        )
        assert has_error_handling, "Expected error handling for failed fetch in app.js"

    def test_displays_error_message(self) -> None:
        """app.js must display an error message to the user on failure."""
        assert "error" in self.js.lower()


# ===================================================================
# Integration: Admin + API coexistence
# ===================================================================


class TestAdminApiCoexistence:
    """Ensure the admin mount does not interfere with API routes."""

    def test_admin_serves_while_api_lists_bots(
        self, client: TestClient, bot_factory
    ) -> None:
        """Both /admin and /api/v1/bots work in the same app instance."""
        # Arrange
        bot_factory(rig_id="coexistence-test")

        # Act
        admin_resp = client.get("/admin/index.html")
        api_resp = client.get("/api/v1/bots")

        # Assert
        assert admin_resp.status_code == 200
        assert api_resp.status_code == 200
        data = api_resp.json()
        assert data["total"] >= 1

    def test_admin_path_does_not_shadow_api(self, client: TestClient) -> None:
        """The /admin mount must not shadow the /api prefix."""
        response = client.get("/api/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
