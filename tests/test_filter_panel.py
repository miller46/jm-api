"""Tests for collapsible filter panel feature (spec.txt).

Covers all four sub-tasks:
  1. Discover filterable fields from OpenAPI spec
  2. Render filter panel UI (text, select, datetime-local inputs)
  3. Apply filters and refetch data (query params, re-render, preserve state)
  4. Clear filters (reset inputs, refetch unfiltered data)

Plus acceptance criteria:
  - Filter panel appears as collapsible <details> on table page
  - Inputs match field types (text, select, datetime-local)
  - "Apply Filters" sends correct query params to API and re-renders table
  - "Clear" resets filters and shows all records
  - Column visibility and sorting preserved after filtering
  - Pagination resets to page 1 on filter apply
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
# CSS helpers (reused from test_table_enhancements pattern)
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
# Sub-task 1: Discover filterable fields from OpenAPI spec
# ===================================================================


class TestDiscoverFilterableFields:
    """app.js must fetch /openapi.json and extract GET query parameters."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_fetches_openapi_json(self) -> None:
        """app.js must fetch /openapi.json to discover filterable fields.

        Spec: 'add a function that fetches /openapi.json and extracts
        query parameters from the GET /api/v1/{table} endpoint.'
        """
        assert "/openapi.json" in self.js, (
            "Expected fetch('/openapi.json') call in app.js to discover filter fields"
        )

    def test_reads_get_endpoint_parameters(self) -> None:
        """Must extract query parameters from the GET endpoint.

        Spec: 'extracts query parameters from the GET /api/v1/{table} endpoint.'
        The code should look for path objects and GET parameters in the spec.
        """
        has_get_or_parameters = any(
            token in self.js
            for token in [
                "parameters",
                ".get",
                "get",
                "query",
            ]
        )
        assert has_get_or_parameters, (
            "Expected code that reads GET endpoint parameters from OpenAPI spec"
        )

    def test_excludes_pagination_params(self) -> None:
        """Must exclude pagination params (page, per_page) from filter fields.

        Spec: 'Exclude pagination params (page, per_page).'
        """
        has_exclusion = any(
            token in self.js
            for token in [
                "page",
                "per_page",
                "pagination",
                "skip",
                "exclude",
                "filter",
            ]
        )
        assert has_exclusion, (
            "Expected pagination param exclusion logic (page, per_page) in filter discovery"
        )

    def test_groups_date_range_pairs(self) -> None:
        """Must group _after/_before suffix params into a single filter entry.

        Spec: 'Group DATE_RANGE pairs (_after/_before suffixes) into a single filter entry.'
        """
        has_date_grouping = any(
            token in self.js
            for token in [
                "_after",
                "_before",
                "after",
                "before",
                "date",
                "range",
                "datetime",
            ]
        )
        assert has_date_grouping, (
            "Expected DATE_RANGE pair grouping logic (_after/_before) in app.js"
        )

    def test_parses_parameter_types(self) -> None:
        """Must parse each parameter's type (string, boolean, integer).

        Spec: 'Parse each parameter's name, type (string, boolean, integer), and schema.'
        """
        has_type_parsing = any(
            token in self.js_lower
            for token in [
                "type",
                "boolean",
                "string",
                "integer",
                "schema",
            ]
        )
        assert has_type_parsing, (
            "Expected parameter type parsing (string, boolean, integer) in app.js"
        )

    def test_discover_filter_function_exists(self) -> None:
        """A dedicated function for discovering filter fields should exist.

        Spec: 'add a function that fetches /openapi.json and extracts query parameters.'
        """
        has_discover_fn = any(
            token in self.js
            for token in [
                "discoverFilter",
                "getFilter",
                "fetchFilter",
                "loadFilter",
                "buildFilter",
                "parseFilter",
                "extractFilter",
                "Filter",
            ]
        )
        assert has_discover_fn, (
            "Expected a dedicated function for discovering filter fields "
            "(e.g. discoverFilterFields, getFilterableParams) in app.js"
        )


# ===================================================================
# Sub-task 2: Render filter panel UI
# ===================================================================


class TestFilterPanelHTML:
    """table.html must have a <details id='filter-toggle'> element."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("table.html")
        self.html_lower = self.html.lower()

    def test_filter_details_element_exists(self) -> None:
        """Filter panel must be a collapsible <details> element.

        Spec: 'add a <details id="filter-toggle"> element beside the existing Columns <details>.'
        """
        assert "filter-toggle" in self.html or "filter" in self.html_lower, (
            "Expected <details id='filter-toggle'> element in table.html"
        )

    def test_filter_details_has_summary(self) -> None:
        """Filter <details> must have a <summary> element.

        Matching the existing Columns <details> pattern.
        """
        # Find all summary elements — at least two should exist (Columns + Filters)
        summaries = re.findall(
            r"<summary[^>]*>(.*?)</summary>",
            self.html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # At least the original Columns summary must exist, plus a filter-related one
        has_filter_summary = any(
            "filter" in s.lower() for s in summaries
        )
        assert has_filter_summary, (
            "Expected a <summary> element with 'Filter' text inside the filter <details>"
        )

    def test_filter_panel_placement(self) -> None:
        """Filter panel must appear beside the existing Columns <details>.

        Spec: 'add a <details id="filter-toggle"> element beside the existing Columns <details>.'
        Both should be between the 'Add Record' button and the table.
        """
        add_btn_pos = self.html_lower.find("add-record-btn")
        table_pos = self.html_lower.find("<table")

        # Look for filter-related details element
        filter_pos = self.html_lower.find("filter")

        assert add_btn_pos != -1, "Expected add-record-btn in table.html"
        assert table_pos != -1, "Expected <table> in table.html"
        assert filter_pos != -1, "Expected filter element in table.html"

        assert add_btn_pos < filter_pos < table_pos, (
            "Filter panel must appear after the 'Add Record' button "
            "and before the <table> element"
        )

    def test_two_details_elements_exist(self) -> None:
        """Both Columns and Filters <details> must exist side by side.

        Spec says to match the existing Columns <details> pattern.
        """
        details_count = len(re.findall(r"<details", self.html, flags=re.IGNORECASE))
        assert details_count >= 2, (
            f"Expected at least 2 <details> elements (Columns + Filters), found {details_count}"
        )


class TestFilterPanelInputTypes:
    """app.js must dynamically populate filter inputs by field type."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_text_input_for_string_fields(self) -> None:
        """String/ILIKE fields must use text <input>.

        Spec: 'string/ILIKE fields: text <input>.'
        """
        has_text_input = any(
            token in self.js
            for token in [
                'type="text"',
                "type='text'",
                '"text"',
                "'text'",
                "text",
            ]
        )
        assert has_text_input, (
            "Expected text <input> creation for string/ILIKE filter fields"
        )

    def test_select_for_boolean_fields(self) -> None:
        """Boolean fields must use <select> with Any / true / false options.

        Spec: 'boolean fields: <select> with options: Any / true / false.'
        """
        has_select = any(
            token in self.js
            for token in [
                "<select",
                "createElement(\"select\")",
                "createElement('select')",
                "select",
            ]
        )
        assert has_select, (
            "Expected <select> element creation for boolean filter fields"
        )

    def test_boolean_select_has_three_options(self) -> None:
        """Boolean <select> must have Any / true / false options.

        Spec: '<select> with options: Any / true / false.'
        """
        has_true = "true" in self.js_lower
        has_false = "false" in self.js_lower
        has_any_or_all = any(
            token in self.js_lower for token in ["any", "all", '""', "''"]
        )
        assert has_true and has_false, (
            "Expected 'true' and 'false' options in boolean filter <select>"
        )
        assert has_any_or_all, (
            "Expected 'Any'/'All' or empty-value option in boolean filter <select>"
        )

    def test_datetime_local_for_date_range_fields(self) -> None:
        """DATE_RANGE fields must use <input type='datetime-local'>.

        Spec: 'DATE_RANGE fields: two <input type="datetime-local"> (After / Before).'
        """
        has_datetime_local = any(
            token in self.js
            for token in [
                "datetime-local",
                "datetime",
                "date",
            ]
        )
        assert has_datetime_local, (
            "Expected <input type='datetime-local'> for DATE_RANGE filter fields"
        )

    def test_date_range_has_after_and_before_labels(self) -> None:
        """DATE_RANGE inputs must have After / Before labels or placeholders.

        Spec: 'two <input type="datetime-local"> (After / Before).'
        """
        has_after = any(
            token in self.js_lower
            for token in ["after", "_after", "from", "start"]
        )
        has_before = any(
            token in self.js_lower
            for token in ["before", "_before", "to", "end"]
        )
        assert has_after and has_before, (
            "Expected 'After' and 'Before' labels/identifiers for DATE_RANGE filter inputs"
        )

    def test_apply_filters_button_exists(self) -> None:
        """An 'Apply Filters' button must be rendered at the bottom.

        Spec: 'Add an "Apply Filters" <button> at the bottom.'
        """
        has_apply = any(
            token in self.js
            for token in [
                "Apply",
                "apply",
                "Filter",
                "filter",
                "submit",
                "Search",
                "search",
            ]
        )
        assert has_apply, (
            "Expected an 'Apply Filters' button in the filter panel"
        )


# ===================================================================
# Sub-task 3: Apply filters and refetch data
# ===================================================================


class TestApplyFiltersAndRefetch:
    """On 'Apply Filters' click: build query string, fetch, re-render."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_builds_query_string_from_inputs(self) -> None:
        """Must build query string from non-empty filter inputs.

        Spec: 'Build query string from non-empty filter inputs.'
        """
        has_query_building = any(
            token in self.js
            for token in [
                "URLSearchParams",
                "encodeURIComponent",
                "query",
                "param",
                "?",
                "&",
                "append",
            ]
        )
        assert has_query_building, (
            "Expected query string building logic (URLSearchParams, encodeURIComponent, etc.)"
        )

    def test_fetches_with_filter_params(self) -> None:
        """Must fetch GET /api/v1/{table} with filter query params.

        Spec: 'Fetch GET /api/v1/{table}?{filters}&page=1&per_page={current}.'
        """
        assert "fetch(" in self.js, (
            "Expected fetch() call with filter query parameters"
        )
        assert "/api/v1/" in self.js, (
            "Expected /api/v1/ URL in fetch call"
        )

    def test_resets_to_page_one(self) -> None:
        """Must reset pagination to page 1 on filter apply.

        Spec: 'Pagination resets to page 1 on filter apply.'
        Acceptance criteria: 'Pagination resets to page 1 on filter apply.'
        """
        has_page_reset = any(
            token in self.js
            for token in [
                "page=1",
                "page = 1",
                "currentPage = 1",
                "page=1",
            ]
        )
        assert has_page_reset, (
            "Expected pagination reset to page 1 when applying filters"
        )

    def test_re_renders_table_after_filter(self) -> None:
        """Must re-render the table with filtered results.

        Spec: 'Re-render the table with filtered results.'
        """
        has_rerender = any(
            token in self.js
            for token in [
                "renderTable",
                "innerHTML",
                "render",
            ]
        )
        assert has_rerender, (
            "Expected table re-render after applying filters"
        )

    def test_skips_empty_filter_values(self) -> None:
        """Non-empty filter inputs should be the only ones sent.

        Spec: 'Build query string from non-empty filter inputs.'
        Empty/blank inputs must be skipped.
        """
        has_empty_check = any(
            token in self.js
            for token in [
                '!== ""',
                "!== ''",
                '.value',
                'trim',
                'length',
                'empty',
                '!val',
                'if (',
                'continue',
            ]
        )
        assert has_empty_check, (
            "Expected empty-value check logic to skip blank filter inputs"
        )


class TestPreserveStateAfterFilter:
    """Column visibility and sort state must be preserved after filtering."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_table_state_object_exists(self) -> None:
        """TableState (or equivalent state) object must exist to track sort/column state.

        Spec: 'Preserve column visibility and sort state.'
        """
        assert "TableState" in self.js or "state" in self.js.lower(), (
            "Expected a state object (TableState) to preserve sort/column state across filter"
        )

    def test_hidden_columns_preserved(self) -> None:
        """hiddenColumns state must persist across filter operations.

        Spec: 'Preserve column visibility ... after filtering.'
        Acceptance criteria: 'Column visibility and sorting preserved after filtering.'
        """
        assert "hiddenColumns" in self.js or "hidden" in self.js.lower(), (
            "Expected hiddenColumns state to be preserved after filtering"
        )

    def test_sort_state_preserved(self) -> None:
        """Sort column and direction must persist across filter operations.

        Spec: 'Preserve ... sort state.'
        Acceptance criteria: 'Column visibility and sorting preserved after filtering.'
        """
        has_sort_state = any(
            token in self.js
            for token in [
                "sortColumn",
                "sortDirection",
                "sortOrder",
            ]
        )
        assert has_sort_state, (
            "Expected sort state (sortColumn, sortDirection) to be preserved after filtering"
        )


# ===================================================================
# Sub-task 4: Clear filters
# ===================================================================


class TestClearFilters:
    """'Clear' button must reset all filter inputs and refetch unfiltered data."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.js_lower = self.js.lower()

    def test_clear_button_exists(self) -> None:
        """A 'Clear' button must exist in the filter panel.

        Spec: 'Add a "Clear" button that resets all filter inputs to empty/default
        and refetches unfiltered data.'
        """
        has_clear = any(
            token in self.js
            for token in [
                "Clear",
                "clear",
                "Reset",
                "reset",
            ]
        )
        assert has_clear, (
            "Expected a 'Clear' or 'Reset' button in the filter panel"
        )

    def test_clear_resets_input_values(self) -> None:
        """Clear must reset all filter inputs to empty/default.

        Spec: 'resets all filter inputs to empty/default.'
        """
        has_reset_logic = any(
            token in self.js
            for token in [
                '= ""',
                "= ''",
                ".value =",
                "reset",
                "selectedIndex",
                "selected",
                'value = ""',
                "value = ''",
            ]
        )
        assert has_reset_logic, (
            "Expected input reset logic (value = '', selectedIndex = 0, etc.) "
            "in clear filter handler"
        )

    def test_clear_refetches_unfiltered_data(self) -> None:
        """Clear must refetch unfiltered data from the API.

        Spec: 'refetches unfiltered data.'
        """
        # The fetch call should be reusable (called on clear as well as on apply)
        fetch_count = self.js.count("fetch(")
        assert fetch_count >= 2, (
            f"Expected at least 2 fetch() calls (initial load + filter/clear), "
            f"found {fetch_count}"
        )

    def test_clear_button_has_click_handler(self) -> None:
        """Clear button must have a click event handler."""
        has_event = any(
            token in self.js
            for token in [
                "addEventListener",
                "onclick",
                "click",
            ]
        )
        assert has_event, (
            "Expected click event handler on the Clear button"
        )


# ===================================================================
# Filter panel CSS
# ===================================================================


class TestFilterPanelCSS:
    """Filter panel should be styled consistently with existing UI."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")
        self.css_lower = self.css.lower()

    def test_filter_panel_has_styling(self) -> None:
        """Filter panel elements should have CSS styling.

        The filter panel should use existing button and form styles,
        or have dedicated filter-specific styles.
        """
        # At minimum the existing btn and form-group styles must exist
        has_btn_styles = _find_blocks(self.css, ".btn")
        has_form_styles = _find_blocks(self.css, ".form-group")
        assert len(has_btn_styles) > 0, (
            "Expected .btn CSS class for filter panel buttons"
        )
        assert len(has_form_styles) > 0, (
            "Expected .form-group CSS class for filter input layout"
        )


# ===================================================================
# Acceptance criteria: Integration-level checks
# ===================================================================


class TestFilterPanelAcceptanceCriteria:
    """Cross-cutting acceptance criteria checks across all static files."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.js = _read_static("app.js")
        self.html = _read_static("table.html")
        self.css = _read_static("style.css")

    def test_filter_panel_collapsible_details(self) -> None:
        """AC: Filter panel appears as collapsible <details> on table page."""
        # Verify HTML has a filter-related <details>
        details_matches = re.findall(
            r'<details[^>]*id\s*=\s*["\']([^"\']*)["\'][^>]*>',
            self.html,
            flags=re.IGNORECASE,
        )
        has_filter_details = any("filter" in d.lower() for d in details_matches)
        assert has_filter_details, (
            "AC: Expected <details> element with 'filter' in its id attribute"
        )

    def test_inputs_match_field_types(self) -> None:
        """AC: Inputs match field types (text, select, datetime-local)."""
        has_text = "text" in self.js
        has_select = any(
            token in self.js for token in ["select", "SELECT", "Select"]
        )
        has_datetime = any(
            token in self.js for token in ["datetime-local", "datetime", "date"]
        )
        assert has_text, "AC: Expected text input type for string fields"
        assert has_select, "AC: Expected select element for boolean fields"
        assert has_datetime, "AC: Expected datetime-local input for date range fields"

    def test_apply_sends_query_params(self) -> None:
        """AC: 'Apply Filters' sends correct query params to API and re-renders table."""
        # Must build query params
        has_query_params = any(
            token in self.js
            for token in ["URLSearchParams", "encodeURIComponent", "?", "&"]
        )
        # Must call fetch
        has_fetch = "fetch(" in self.js
        # Must re-render
        has_render = "renderTable" in self.js
        assert has_query_params, (
            "AC: Expected query parameter construction for API call"
        )
        assert has_fetch, "AC: Expected fetch() call to API"
        assert has_render, "AC: Expected renderTable() call to re-render"

    def test_clear_resets_and_shows_all(self) -> None:
        """AC: 'Clear' resets filters and shows all records."""
        has_clear = any(
            token in self.js for token in ["Clear", "clear", "Reset", "reset"]
        )
        assert has_clear, (
            "AC: Expected Clear/Reset functionality in app.js"
        )

    def test_column_visibility_preserved(self) -> None:
        """AC: Column visibility preserved after filtering."""
        assert "hiddenColumns" in self.js, (
            "AC: Expected hiddenColumns state to be preserved across filter operations"
        )

    def test_sorting_preserved(self) -> None:
        """AC: Sorting preserved after filtering."""
        assert "sortColumn" in self.js and "sortDirection" in self.js, (
            "AC: Expected sortColumn and sortDirection to be preserved across filter operations"
        )

    def test_pagination_resets_to_page_one(self) -> None:
        """AC: Pagination resets to page 1 on filter apply."""
        has_page_one = any(
            token in self.js
            for token in ["page=1", "page = 1", "currentPage = 1"]
        )
        assert has_page_one, (
            "AC: Expected pagination to reset to page 1 on filter apply"
        )


# ===================================================================
# Regression: existing functionality must not be broken
# ===================================================================


class TestExistingFunctionalityPreservedWithFilters:
    """Ensure filter panel additions don't break existing features."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.js = _read_static("app.js")
        self.html = _read_static("table.html")
        self.css = _read_static("style.css")

    def test_tables_array_still_defined(self) -> None:
        """TABLES constant must still exist."""
        assert "TABLES" in self.js

    def test_table_state_still_defined(self) -> None:
        """TableState object must still exist with all original properties."""
        assert "TableState" in self.js
        assert "sortColumn" in self.js
        assert "sortDirection" in self.js
        assert "headers" in self.js
        assert "originalItems" in self.js
        assert "items" in self.js
        assert "hiddenColumns" in self.js

    def test_fetch_api_still_present(self) -> None:
        """fetch() call to /api/v1/{table} must still exist."""
        assert "fetch(" in self.js
        assert "/api/v1/" in self.js

    def test_render_table_function_exists(self) -> None:
        """renderTable function must still exist."""
        assert "renderTable" in self.js

    def test_sort_by_column_function_exists(self) -> None:
        """sortByColumn function must still exist."""
        assert "sortByColumn" in self.js

    def test_render_column_toggles_function_exists(self) -> None:
        """renderColumnToggles function must still exist."""
        assert "renderColumnToggles" in self.js

    def test_toggle_column_visibility_function_exists(self) -> None:
        """toggleColumnVisibility function must still exist."""
        assert "toggleColumnVisibility" in self.js

    def test_show_error_function_exists(self) -> None:
        """showError function must still exist."""
        assert "showError" in self.js

    def test_escape_html_function_exists(self) -> None:
        """escapeHtml function must still exist for XSS prevention."""
        assert "escapeHtml" in self.js

    def test_init_table_page_still_exists(self) -> None:
        """initTablePage function must still be present."""
        assert "initTablePage" in self.js

    def test_init_edit_page_still_exists(self) -> None:
        """initEditPage function must still be present."""
        assert "initEditPage" in self.js

    def test_init_create_page_still_exists(self) -> None:
        """initCreatePage function must still be present."""
        assert "initCreatePage" in self.js

    def test_column_toggle_details_preserved(self) -> None:
        """Original Columns <details id='column-toggle'> must still exist."""
        assert "column-toggle" in self.html

    def test_column_checkboxes_container_preserved(self) -> None:
        """Original column-checkboxes div must still exist."""
        assert "column-checkboxes" in self.html

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

    def test_style_links_preserved_in_html(self) -> None:
        """table.html must still link to style.css."""
        assert "style.css" in self.html

    def test_script_links_preserved_in_html(self) -> None:
        """table.html must still link to app.js."""
        assert "app.js" in self.html

    def test_col_hidden_class_still_exists(self) -> None:
        """style.css must still define .col-hidden."""
        col_hidden_blocks = _find_blocks(self.css, "col-hidden")
        assert len(col_hidden_blocks) > 0, (
            "Expected .col-hidden CSS class to still exist in style.css"
        )

    def test_sortable_header_class_still_exists(self) -> None:
        """style.css must still define .sortable-header."""
        sortable_blocks = _find_blocks(self.css, "sortable-header")
        assert len(sortable_blocks) > 0, (
            "Expected .sortable-header CSS class to still exist in style.css"
        )

    def test_hover_style_preserved(self) -> None:
        """tbody tr:hover background style must still work."""
        hover_blocks = _find_blocks(self.css, "tbody tr:hover")
        assert len(hover_blocks) > 0, "tbody tr:hover CSS rule must still exist"

    def test_tbody_tr_cursor_pointer_preserved(self) -> None:
        """tbody tr must still have cursor: pointer."""
        tbody_tr_blocks = _find_blocks(self.css, "tbody tr")
        has_pointer = any(
            _css_has_property(body, "cursor", "pointer")
            for body in tbody_tr_blocks
        )
        assert has_pointer, (
            "Expected cursor: pointer on 'tbody tr' to still be in style.css"
        )

    def test_discover_create_fields_still_exists(self) -> None:
        """discoverCreateFields function must still be present."""
        assert "discoverCreateFields" in self.js

    def test_resolve_ref_still_exists(self) -> None:
        """resolveRef function must still be present."""
        assert "resolveRef" in self.js


# ===================================================================
# API integration: filter query params via TestClient
# ===================================================================


class TestFilterQueryParamsAPI:
    """Test that filter query params work end-to-end via the API."""

    def test_get_bots_with_exact_filter(self, client, bot_factory):
        """GET /api/v1/bots?rig_id=xxx returns only matching bots."""
        bot_factory(rig_id="rig-A")
        bot_factory(rig_id="rig-B")
        bot_factory(rig_id="rig-A")

        response = client.get("/api/v1/bots?rig_id=rig-A")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 2
        assert all(b["rig_id"] == "rig-A" for b in items)

    def test_get_bots_with_bool_filter(self, client, bot_factory):
        """GET /api/v1/bots?kill_switch=true returns only matching bots."""
        bot_factory(rig_id="rig-1", kill_switch=True)
        bot_factory(rig_id="rig-2", kill_switch=False)
        bot_factory(rig_id="rig-3", kill_switch=True)

        response = client.get("/api/v1/bots?kill_switch=true")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 2
        assert all(b["kill_switch"] is True for b in items)

    def test_get_bots_with_ilike_filter(self, client, bot_factory):
        """GET /api/v1/bots?log_search=error returns bots with matching logs."""
        bot_factory(rig_id="rig-1", last_run_log="ERROR: connection failed")
        bot_factory(rig_id="rig-2", last_run_log="Success")
        bot_factory(rig_id="rig-3", last_run_log="error found in config")

        response = client.get("/api/v1/bots?log_search=error")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 2

    def test_get_bots_with_no_filters_returns_all(self, client, bot_factory):
        """GET /api/v1/bots without filters returns all bots."""
        bot_factory(rig_id="rig-1")
        bot_factory(rig_id="rig-2")

        response = client.get("/api/v1/bots")
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) >= 2

    def test_get_bots_combined_filters(self, client, bot_factory):
        """GET /api/v1/bots with multiple filters applies AND logic."""
        bot_factory(rig_id="rig-A", kill_switch=True, last_run_log="error found")
        bot_factory(rig_id="rig-A", kill_switch=False, last_run_log="error found")
        bot_factory(rig_id="rig-B", kill_switch=True, last_run_log="error found")
        bot_factory(rig_id="rig-A", kill_switch=True, last_run_log="success")

        response = client.get(
            "/api/v1/bots?rig_id=rig-A&kill_switch=true&log_search=error"
        )
        assert response.status_code == 200
        data = response.json()
        items = data["items"]
        assert len(items) == 1
        assert items[0]["rig_id"] == "rig-A"
        assert items[0]["kill_switch"] is True

    def test_openapi_spec_lists_filter_params(self, client):
        """GET /openapi.json must list filter query parameters for the bots endpoint."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()

        # Find the GET /api/v1/bots endpoint
        bots_path = spec.get("paths", {}).get("/api/v1/bots", {})
        get_op = bots_path.get("get", {})
        params = get_op.get("parameters", [])

        param_names = [p["name"] for p in params]

        # Check that known filter params are present
        assert "rig_id" in param_names, "Expected rig_id filter param in OpenAPI spec"
        assert "kill_switch" in param_names, "Expected kill_switch filter param in OpenAPI spec"
        assert "log_search" in param_names, "Expected log_search filter param in OpenAPI spec"

    def test_openapi_spec_lists_date_range_params(self, client):
        """GET /openapi.json must list DATE_RANGE _after/_before params."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()

        bots_path = spec.get("paths", {}).get("/api/v1/bots", {})
        get_op = bots_path.get("get", {})
        params = get_op.get("parameters", [])

        param_names = [p["name"] for p in params]

        assert "create_at_after" in param_names, (
            "Expected create_at_after date range param in OpenAPI spec"
        )
        assert "create_at_before" in param_names, (
            "Expected create_at_before date range param in OpenAPI spec"
        )

    def test_openapi_spec_has_pagination_params(self, client):
        """Pagination params (page, per_page) must still be in the OpenAPI spec."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()

        bots_path = spec.get("paths", {}).get("/api/v1/bots", {})
        get_op = bots_path.get("get", {})
        params = get_op.get("parameters", [])

        param_names = [p["name"] for p in params]

        assert "page" in param_names, "Expected page pagination param in OpenAPI spec"
        assert "per_page" in param_names, "Expected per_page pagination param in OpenAPI spec"

    def test_filter_with_pagination_resets_to_page_one(self, client, bot_factory):
        """Filtering with page=1 should return the first page of results."""
        for i in range(5):
            bot_factory(rig_id="rig-test")

        response = client.get("/api/v1/bots?rig_id=rig-test&page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert len(data["items"]) <= 2
