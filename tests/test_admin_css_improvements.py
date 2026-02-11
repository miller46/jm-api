"""Tests for admin dashboard CSS improvements (spec.txt).

Spec tasks:
  1. Add spacing (margin-bottom: 1.5rem) between "Add Record" button and table
  2. Minor CSS polish:
     a. border-radius: 4px on table and .table-wrapper
     b. "Back to dashboard" link on table.html and create.html
     c. margin-bottom: 0.5rem on h1 on table page
"""

import pathlib
import re

import pytest

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ---------------------------------------------------------------------------
# Helpers for CSS parsing
# ---------------------------------------------------------------------------


def _css_blocks(css: str) -> list[tuple[str, str]]:
    """Return list of (selector, body) tuples from CSS text.

    Simple parser — handles single-level blocks only (no nested @media etc.).
    Strips comments first.
    """
    # Strip /* ... */ comments
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        selector = match.group(1).strip()
        body = match.group(2).strip()
        blocks.append((selector, body))
    return blocks


def _find_blocks(css: str, selector_pattern: str) -> list[str]:
    """Return CSS bodies for all selectors matching *selector_pattern* (substring)."""
    return [body for sel, body in _css_blocks(css) if selector_pattern in sel]


def _css_has_property(body: str, prop: str, value: str) -> bool:
    """Check if a CSS body string contains ``prop: value``."""
    # Normalise whitespace around colons and semicolons
    pattern = rf"{re.escape(prop)}\s*:\s*{re.escape(value)}"
    return bool(re.search(pattern, body))


# ===================================================================
# Task 1: Spacing between "Add Record" button and the table
# ===================================================================


class TestButtonTableSpacing:
    """The 'Add Record' button must have margin-bottom: 1.5rem so it
    doesn't sit flush against the data table."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.css = _read_static("style.css")
        self.table_html = _read_static("table.html")

    # -- Approach A: scoped via .action-bar wrapper --

    def test_action_bar_wrapper_or_btn_margin(self) -> None:
        """Either .action-bar wrapper in HTML with margin-bottom: 1.5rem in CSS,
        or .btn itself must have margin-bottom: 1.5rem."""
        has_action_bar_html = "action-bar" in self.table_html
        has_action_bar_css = any(
            _css_has_property(body, "margin-bottom", "1.5rem")
            for body in _find_blocks(self.css, "action-bar")
        )

        has_btn_margin = any(
            _css_has_property(body, "margin-bottom", "1.5rem")
            for body in _find_blocks(self.css, ".btn")
        )

        action_bar_approach = has_action_bar_html and has_action_bar_css
        btn_approach = has_btn_margin

        assert action_bar_approach or btn_approach, (
            "Expected margin-bottom: 1.5rem on .action-bar wrapper or .btn "
            "to add spacing between the Add Record button and the table"
        )

    def test_margin_bottom_value_is_1_5rem(self) -> None:
        """The spacing value must be exactly 1.5rem (not 1rem, 2rem, etc.)."""
        assert "1.5rem" in self.css, (
            "Expected '1.5rem' value in style.css for button-table spacing"
        )


# ===================================================================
# Task 2a: border-radius: 4px on table and .table-wrapper
# ===================================================================


class TestTableBorderRadius:
    """table and .table-wrapper must have border-radius: 4px."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_table_has_border_radius(self) -> None:
        """The 'table' selector must include border-radius: 4px."""
        table_blocks = _find_blocks(self.css, "table")
        # Filter to blocks where selector is exactly "table" (not .table-wrapper, etc.)
        exact_table_blocks = [
            body
            for sel, body in _css_blocks(self.css)
            if re.fullmatch(r"table", sel.strip())
        ]
        has_radius = any(
            _css_has_property(body, "border-radius", "4px")
            for body in exact_table_blocks
        )
        assert has_radius, (
            "Expected border-radius: 4px in the 'table' CSS rule"
        )

    def test_table_wrapper_has_border_radius(self) -> None:
        """The '.table-wrapper' selector must include border-radius: 4px."""
        wrapper_blocks = _find_blocks(self.css, ".table-wrapper")
        has_radius = any(
            _css_has_property(body, "border-radius", "4px")
            for body in wrapper_blocks
        )
        assert has_radius, (
            "Expected border-radius: 4px in the '.table-wrapper' CSS rule"
        )


# ===================================================================
# Task 2b: "Back to dashboard" link on table.html and create.html
# ===================================================================


class TestBackToDashboardLink:
    """table.html and create.html must have a 'Back to dashboard' link."""

    def test_table_html_has_back_link(self) -> None:
        """table.html must contain a link back to the dashboard."""
        html = _read_static("table.html")
        html_lower = html.lower()
        # Must have an anchor linking to index.html (or /admin or /admin/)
        has_back_link = (
            "index.html" in html
            or 'href="/admin"' in html_lower
            or 'href="/admin/"' in html_lower
        )
        assert has_back_link, (
            "table.html must contain a link back to the dashboard (index.html)"
        )

    def test_table_html_back_link_text(self) -> None:
        """table.html back link must contain 'dashboard' text."""
        html = _read_static("table.html")
        html_lower = html.lower()
        assert "dashboard" in html_lower, (
            "table.html back link text must mention 'dashboard'"
        )

    def test_create_html_has_back_link(self) -> None:
        """create.html must contain a link back to the dashboard."""
        html = _read_static("create.html")
        html_lower = html.lower()
        has_back_link = (
            "index.html" in html
            or 'href="/admin"' in html_lower
            or 'href="/admin/"' in html_lower
        )
        assert has_back_link, (
            "create.html must contain a link back to the dashboard (index.html)"
        )

    def test_create_html_back_link_text(self) -> None:
        """create.html back link must contain 'dashboard' text."""
        html = _read_static("create.html")
        html_lower = html.lower()
        assert "dashboard" in html_lower, (
            "create.html back link text must mention 'dashboard'"
        )

    def test_table_html_back_link_is_anchor_element(self) -> None:
        """The back link in table.html must be an <a> element (not a button)."""
        html = _read_static("table.html")
        # Find an anchor whose text or context mentions "dashboard"
        assert re.search(
            r"<a\s[^>]*>.*?dashboard.*?</a>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ), "table.html must use an <a> element for the back-to-dashboard link"

    def test_create_html_back_link_is_anchor_element(self) -> None:
        """The back link in create.html must be an <a> element (not a button)."""
        html = _read_static("create.html")
        assert re.search(
            r"<a\s[^>]*>.*?dashboard.*?</a>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        ), "create.html must use an <a> element for the back-to-dashboard link"


# ===================================================================
# Task 2c: margin-bottom: 0.5rem on h1 on the table page
# ===================================================================


class TestTablePageH1Spacing:
    """h1 on the table page must have margin-bottom: 0.5rem for
    consistent heading spacing."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_h1_margin_bottom_is_half_rem(self) -> None:
        """CSS must set margin-bottom: 0.5rem on h1.

        The spec says the h1 on the table page should have 0.5rem margin-bottom.
        This can be scoped globally or specifically.
        """
        h1_blocks = [
            body
            for sel, body in _css_blocks(self.css)
            if "h1" in sel
        ]
        has_half_rem = any(
            _css_has_property(body, "margin-bottom", "0.5rem")
            for body in h1_blocks
        )
        assert has_half_rem, (
            "Expected margin-bottom: 0.5rem on h1 in style.css"
        )


# ===================================================================
# Regression: existing styles must not be broken
# ===================================================================


class TestExistingStylesPreserved:
    """Ensure the targeted fixes don't break existing CSS rules."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")
        self.css_lower = self.css.lower()

    def test_system_font_stack_preserved(self) -> None:
        """System font stack must still be present."""
        assert "system-ui" in self.css_lower

    def test_max_width_preserved(self) -> None:
        """max-width on main container still present."""
        assert "max-width" in self.css_lower

    def test_table_border_collapse_preserved(self) -> None:
        """Table border-collapse must still be present."""
        assert "border-collapse" in self.css_lower

    def test_alternating_rows_preserved(self) -> None:
        """nth-child alternating row styles must still exist."""
        assert "nth-child" in self.css_lower

    def test_overflow_x_preserved(self) -> None:
        """Horizontal scroll overflow must still exist."""
        assert "overflow-x" in self.css_lower

    def test_btn_primary_preserved(self) -> None:
        """.btn-primary styles must still exist."""
        assert ".btn-primary" in self.css

    def test_form_group_preserved(self) -> None:
        """.form-group styles must still exist."""
        assert ".form-group" in self.css

    def test_loading_class_preserved(self) -> None:
        """.loading class must still exist."""
        assert ".loading" in self.css

    def test_error_class_preserved(self) -> None:
        """.error class must still exist."""
        assert ".error" in self.css


# ===================================================================
# Regression: HTML structure must not be broken
# ===================================================================


class TestHtmlStructurePreserved:
    """Ensure HTML templates still have required elements after changes."""

    def test_table_html_still_has_table_element(self) -> None:
        html = _read_static("table.html")
        assert "<table" in html.lower()

    def test_table_html_still_has_add_record_btn(self) -> None:
        html = _read_static("table.html")
        assert "add-record-btn" in html or "Add Record" in html

    def test_table_html_still_has_loading_indicator(self) -> None:
        html = _read_static("table.html")
        assert "loading" in html.lower()

    def test_table_html_still_has_error_display(self) -> None:
        html = _read_static("table.html")
        assert "error" in html.lower()

    def test_create_html_still_has_form(self) -> None:
        html = _read_static("create.html")
        assert "<form" in html.lower()

    def test_index_html_still_has_table_list(self) -> None:
        html = _read_static("index.html")
        assert "table-list" in html or "<ul" in html.lower()

    def test_create_html_still_links_style_css(self) -> None:
        html = _read_static("create.html")
        assert "style.css" in html

    def test_create_html_still_links_app_js(self) -> None:
        html = _read_static("create.html")
        assert "app.js" in html
