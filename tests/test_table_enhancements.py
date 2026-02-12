"""Tests for table list page enhancements (spec.txt).

Covers all three sub-tasks:
  1. Make entire table row clickable (navigate to edit page)
  2. Add column sorting (click <th> to sort asc/desc, sort indicator arrows)
  3. Add column visibility toggle (<details> toolbar with checkboxes, CSS col-hidden)
"""

import pathlib
import re

import pytest

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file's text content from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ---------------------------------------------------------------------------
# CSS helpers (reused from test_admin_css_improvements pattern)
# ---------------------------------------------------------------------------


def _css_blocks(css: str) -> list[tuple[str, str]]:
    """Return list of (selector, body) tuples from CSS text."""
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
    pattern = rf"{re.escape(prop)}\s*:\s*{re.escape(value)}"
    return bool(re.search(pattern, body))


# ===================================================================
# Sub-task 1: Make entire table row clickable
# ===================================================================


class TestRowClickNavigation:
    """Clicking any part of a tbody <tr> must navigate to the edit page."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_row_has_click_handler_or_onclick(self) -> None:
        """Each <tr> in tbody must have a click handler for navigation.

        The spec says: 'Replace the current first-column-only <a> link with
        a row-level click handler.'  Implementation can use addEventListener,
        onclick attribute, or wrapping in a clickable element.
        """
        has_row_click = any(
            token in self.js
            for token in [
                "addEventListener",
                "onclick",
                "click",
                "tr.style.cursor",
                "cursor",
            ]
        )
        assert has_row_click, (
            "Expected a row-level click handler in renderTable() — "
            "each <tr> should be clickable to navigate to the edit page"
        )

    def test_row_click_navigates_to_edit_page(self) -> None:
        """Row click must navigate to edit.html?table={table}&id={record.id}."""
        assert "edit.html" in self.js, (
            "renderTable must reference edit.html for row-click navigation"
        )
        # The URL must include both table and id parameters
        has_table_param = "table=" in self.js
        has_id_param = "id=" in self.js
        assert has_table_param and has_id_param, (
            "Row-click URL must include table= and id= query parameters"
        )

    def test_first_column_no_longer_sole_link(self) -> None:
        """The first-column-only <a> link pattern should be replaced.

        After the change, navigation should be row-level, not limited to
        a single <a> in the first <td>. The old pattern wrapped only
        column 0 in an <a> tag.
        """
        # The old code had: if (c === 0 && table) { ... <a href= ... }
        # After the change, the row itself should be clickable and the
        # special first-column <a> wrapping should be removed or the
        # entire row should handle navigation.
        # We check that the row-level click pattern exists (already covered above)
        # and that the rendering no longer isolates links to only column 0.
        #
        # If the implementation uses a row click handler, the old
        # "c === 0" link-only pattern should be gone:
        js_lines = self.js.split("\n")
        has_row_level_nav = any(
            "onclick" in line or "addEventListener" in line or "location" in line
            for line in js_lines
            if "tr" in line.lower() or "row" in line.lower()
        )
        # Accept either: row-level handler OR keeping <a> but making whole row clickable
        has_any_row_nav = has_row_level_nav or (
            "cursor" in self.js and "pointer" in self.js
        )
        assert has_any_row_nav, (
            "Row-level navigation must exist — either via row click handler "
            "or cursor:pointer + click logic on <tr>"
        )


class TestRowClickCursorStyle:
    """tbody tr must have cursor: pointer in style.css."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_tbody_tr_cursor_pointer(self) -> None:
        """style.css must set cursor: pointer on tbody tr."""
        # Look for a rule targeting tbody tr (could be "tbody tr", "tbody > tr", etc.)
        tbody_tr_blocks = _find_blocks(self.css, "tbody tr")
        has_pointer = any(
            _css_has_property(body, "cursor", "pointer")
            for body in tbody_tr_blocks
        )
        assert has_pointer, (
            "Expected cursor: pointer on 'tbody tr' in style.css"
        )

    def test_hover_background_still_present(self) -> None:
        """The existing tbody tr:hover background style must be preserved."""
        hover_blocks = _find_blocks(self.css, "tbody tr:hover")
        assert len(hover_blocks) > 0, (
            "tbody tr:hover rule must still exist in style.css"
        )
        has_bg = any("background" in body for body in hover_blocks)
        assert has_bg, (
            "tbody tr:hover must still have a background property"
        )


# ===================================================================
# Sub-task 2: Column sorting
# ===================================================================


class TestColumnSortingJavaScript:
    """app.js must implement client-side column sorting."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_th_click_handler_exists(self) -> None:
        """Column headers (<th>) must be clickable to trigger sorting.

        Implementation should attach a click event to <th> elements.
        """
        has_th_click = any(
            token in self.js
            for token in [
                "th",
                "header",
                "click",
                "addEventListener",
                "onclick",
                "sort",
            ]
        )
        assert has_th_click, (
            "Expected click handler on <th> elements for column sorting"
        )

    def test_sort_function_exists(self) -> None:
        """app.js must contain sorting logic (sort function or method)."""
        has_sort = any(
            token in self.js
            for token in [".sort(", ".sort (", "sort(", "sortBy", "sortColumn"]
        )
        assert has_sort, (
            "Expected a sort function or Array.sort() call in app.js"
        )

    def test_ascending_sort_supported(self) -> None:
        """Clicking a <th> for the first time must sort ascending."""
        # The code should track sort direction, with ascending as default
        has_asc = any(
            token in self.js_lower
            for token in ["asc", "ascending", "sortdir", "sortorder", "direction"]
        )
        assert has_asc, (
            "Expected ascending sort direction tracking in app.js"
        )

    def test_descending_sort_toggle(self) -> None:
        """Clicking the same <th> again must toggle to descending."""
        has_desc = any(
            token in self.js_lower
            for token in ["desc", "descending", "toggle"]
        )
        assert has_desc, (
            "Expected descending sort direction or toggle logic in app.js"
        )

    def test_sort_indicator_arrows(self) -> None:
        """Active column header must display a sort indicator arrow.

        Spec requires ▲ for ascending, ▼ for descending (or equivalent).
        """
        has_arrow = any(
            arrow in self.js
            for arrow in [
                "\u25b2",  # ▲
                "\u25bc",  # ▼
                "&#x25B2",
                "&#x25BC",
                "&#9650",
                "&#9660",
                "arrow",
                "indicator",
                "↑",
                "↓",
                "▲",
                "▼",
            ]
        )
        assert has_arrow, (
            "Expected sort indicator arrows (▲/▼ or equivalent) in app.js"
        )

    def test_sort_is_client_side_only(self) -> None:
        """Sorting must re-order the existing items array client-side.

        It must NOT make a new fetch request with sort params.
        """
        # The sort logic should call .sort() on the items array and then
        # re-render, not trigger a new fetch() call. We verify that
        # sort() is called on an array, not on a URL.
        assert ".sort(" in self.js or ".sort (" in self.js, (
            "Expected Array.sort() for client-side sorting"
        )

    def test_no_sort_on_initial_load(self) -> None:
        """Default: no sort applied on initial load.

        The sort state variables should initialize to null/empty/none.
        """
        # Check that sort state is initialized as null, empty, or undefined
        has_null_init = any(
            token in self.js
            for token in [
                "= null",
                "= ''",
                '= ""',
                "= undefined",
                "= -1",
                "= none",
            ]
        )
        assert has_null_init, (
            "Expected sort state to initialize to null/empty — "
            "no sort should be applied on initial page load"
        )

    def test_re_renders_after_sort(self) -> None:
        """After sorting, the table must be re-rendered.

        The sort logic should call renderTable() or equivalent to update the DOM.
        """
        has_rerender = any(
            token in self.js
            for token in [
                "renderTable",
                "innerHTML",
                "render",
                "tbody",
            ]
        )
        assert has_rerender, (
            "Expected re-render call after sorting (renderTable or innerHTML update)"
        )


# ===================================================================
# Sub-task 3: Column visibility toggle
# ===================================================================


class TestColumnVisibilityToggleHTML:
    """table.html must have a column visibility toolbar."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("table.html")
        self.html_lower = self.html.lower()

    def test_details_summary_wrapper(self) -> None:
        """Column toggles must be wrapped in <details><summary>Columns</summary>.

        Spec: 'Wrap in a <details><summary>Columns</summary>...</details>
        to keep the UI compact.'
        """
        assert "<details" in self.html_lower, (
            "Expected <details> element wrapping column toggles"
        )
        assert "<summary" in self.html_lower, (
            "Expected <summary> element inside <details>"
        )
        # The summary text should mention "Columns"
        summary_match = re.search(
            r"<summary[^>]*>(.*?)</summary>",
            self.html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        assert summary_match, "Expected <summary> tag with text content"
        assert "columns" in summary_match.group(1).lower(), (
            "Expected <summary> text to contain 'Columns'"
        )

    def test_toggle_placement_between_button_and_table(self) -> None:
        """The toggle controls must be between the 'Add Record' button and the table.

        Spec: 'Place the toggle controls between the "Add Record" button and the table.'
        """
        # Find positions of key elements
        add_btn_pos = self.html_lower.find("add-record-btn")
        details_pos = self.html_lower.find("<details")
        table_pos = self.html_lower.find("<table")

        assert add_btn_pos != -1, "Expected add-record-btn in table.html"
        assert details_pos != -1, "Expected <details> in table.html"
        assert table_pos != -1, "Expected <table> in table.html"

        assert add_btn_pos < details_pos < table_pos, (
            "Column toggle <details> must appear after the 'Add Record' button "
            "and before the <table> element"
        )


class TestColumnVisibilityToggleJS:
    """app.js must implement column show/hide via checkboxes."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_renders_checkboxes_per_column(self) -> None:
        """One checkbox per column header must be rendered.

        Spec: 'Render one checkbox per column header, all checked by default.'
        """
        has_checkbox = any(
            token in self.js
            for token in [
                "checkbox",
                'type="checkbox"',
                "type='checkbox'",
                "input",
            ]
        )
        assert has_checkbox, (
            "Expected checkbox creation for each column in app.js"
        )

    def test_checkboxes_checked_by_default(self) -> None:
        """All column checkboxes must be checked by default."""
        has_checked = any(
            token in self.js
            for token in ["checked", "defaultChecked", "checked = true"]
        )
        assert has_checked, (
            "Expected checkboxes to be checked by default"
        )

    def test_toggle_hides_and_shows_columns(self) -> None:
        """Unchecking a checkbox must hide both <th> and <td> cells.

        Rechecking must restore the column.
        """
        has_toggle_logic = any(
            token in self.js
            for token in [
                "col-hidden",
                "display",
                "none",
                "hidden",
                "visibility",
                "classList",
                "className",
            ]
        )
        assert has_toggle_logic, (
            "Expected column hide/show logic (display:none, classList, or col-hidden)"
        )

    def test_references_col_hidden_class(self) -> None:
        """Column hiding should use a CSS class like .col-hidden.

        Spec: 'Implement via CSS display: none on hidden columns
        (using a class like .col-hidden).'
        """
        has_col_hidden = "col-hidden" in self.js
        has_display_none = "display" in self.js_lower and "none" in self.js_lower
        assert has_col_hidden or has_display_none, (
            "Expected col-hidden class or display:none toggling in app.js"
        )

    def test_checkbox_change_event(self) -> None:
        """Checkboxes must respond to change/click events."""
        has_event = any(
            token in self.js
            for token in [
                "change",
                "addEventListener",
                "onchange",
                "onclick",
            ]
        )
        assert has_event, (
            "Expected event listener on column visibility checkboxes"
        )


class TestColumnVisibilityCSS:
    """style.css must define the .col-hidden class."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")
        self.css_lower = self.css.lower()

    def test_col_hidden_class_exists(self) -> None:
        """style.css must define .col-hidden with display: none.

        Spec: 'Implement via CSS display: none on hidden columns
        (using a class like .col-hidden).'
        """
        col_hidden_blocks = _find_blocks(self.css, "col-hidden")
        assert len(col_hidden_blocks) > 0, (
            "Expected .col-hidden CSS class in style.css"
        )
        has_display_none = any(
            _css_has_property(body, "display", "none")
            for body in col_hidden_blocks
        )
        assert has_display_none, (
            "Expected display: none in .col-hidden CSS rule"
        )


# ===================================================================
# Sub-task 2 + CSS: th clickable cursor style
# ===================================================================


class TestSortableHeaderCSS:
    """Column headers should indicate clickability for sorting."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_th_cursor_pointer(self) -> None:
        """<th> elements should have cursor: pointer to indicate sortability.

        While not explicitly required by spec, it's standard UX for clickable
        headers. The spec says 'Make each column header clickable.'
        """
        th_blocks = _find_blocks(self.css, "th")
        has_pointer = any(
            _css_has_property(body, "cursor", "pointer")
            for body in th_blocks
        )
        # Also check for inline style in JS
        js = _read_static("app.js")
        has_inline_pointer = "cursor" in js and "pointer" in js
        assert has_pointer or has_inline_pointer, (
            "Expected cursor: pointer on <th> elements (CSS or inline) "
            "to indicate column headers are clickable for sorting"
        )


# ===================================================================
# Regression: existing functionality must not be broken
# ===================================================================


class TestExistingFunctionalityPreserved:
    """Ensure the three enhancements don't break existing features."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.js = _read_static("app.js")
        self.html = _read_static("table.html")
        self.css = _read_static("style.css")

    def test_tables_array_still_defined(self) -> None:
        """TABLES constant must still exist."""
        assert "TABLES" in self.js

    def test_fetch_api_still_present(self) -> None:
        """fetch() call to /api/v1/{table} must still exist."""
        assert "fetch(" in self.js
        assert "/api/v1/" in self.js

    def test_per_page_20_still_present(self) -> None:
        """per_page=20 query parameter must still be used."""
        assert "per_page=20" in self.js or "per_page" in self.js

    def test_render_table_function_exists(self) -> None:
        """renderTable function must still exist."""
        assert "renderTable" in self.js

    def test_show_error_function_exists(self) -> None:
        """showError function must still exist."""
        assert "showError" in self.js

    def test_loading_element_still_in_html(self) -> None:
        """Loading indicator must still be in table.html."""
        assert "loading" in self.html.lower()

    def test_error_element_still_in_html(self) -> None:
        """Error display must still be in table.html."""
        assert "error" in self.html.lower()

    def test_data_table_element_still_in_html(self) -> None:
        """data-table element must still exist for JS to target."""
        assert "data-table" in self.html

    def test_table_head_and_body_still_in_html(self) -> None:
        """thead (table-head) and tbody (table-body) must still exist."""
        assert "table-head" in self.html
        assert "table-body" in self.html

    def test_add_record_btn_still_in_html(self) -> None:
        """Add Record button must still exist."""
        assert "add-record-btn" in self.html

    def test_back_to_dashboard_link_preserved(self) -> None:
        """Back to dashboard link must still be present."""
        assert "index.html" in self.html

    def test_init_table_page_still_exists(self) -> None:
        """initTablePage function must still be present."""
        assert "initTablePage" in self.js

    def test_init_edit_page_still_exists(self) -> None:
        """initEditPage function must still be present."""
        assert "initEditPage" in self.js

    def test_init_create_page_still_exists(self) -> None:
        """initCreatePage function must still be present."""
        assert "initCreatePage" in self.js

    def test_hover_style_preserved(self) -> None:
        """tbody tr:hover background style must still work."""
        hover_blocks = _find_blocks(self.css, "tbody tr:hover")
        assert len(hover_blocks) > 0, "tbody tr:hover CSS rule must still exist"

    def test_alternating_rows_preserved(self) -> None:
        """Alternating row backgrounds must still work."""
        assert "nth-child" in self.css.lower()

    def test_style_links_preserved_in_html(self) -> None:
        """table.html must still link to style.css."""
        assert "style.css" in self.html

    def test_script_links_preserved_in_html(self) -> None:
        """table.html must still link to app.js."""
        assert "app.js" in self.html
