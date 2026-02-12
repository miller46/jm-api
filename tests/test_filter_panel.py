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
from html.parser import HTMLParser

import pytest

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file's text content from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


# ---------------------------------------------------------------------------
# JS parsing helpers — extract function bodies for structural assertions
# ---------------------------------------------------------------------------


def _extract_js_function_body(js: str, name: str) -> str | None:
    """Extract the full body of a named JS function using brace-counting.

    Handles ``function name(...) { ... }`` declarations.
    Returns the body (including braces) or None if not found.
    """
    pattern = rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{"
    match = re.search(pattern, js)
    if not match:
        return None
    start = match.start()
    depth = 0
    i = match.end() - 1  # position of the opening brace
    while i < len(js):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start : i + 1]
        i += 1
    return None


def _js_function_names(js: str) -> list[str]:
    """Return all top-level ``function xyz(`` names found in *js*."""
    return re.findall(r"^function\s+(\w+)\s*\(", js, flags=re.MULTILINE)


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


# ---------------------------------------------------------------------------
# HTML parser helper — collect element info from HTML
# ---------------------------------------------------------------------------


class _TagCollector(HTMLParser):
    """Collects (tag, attrs-dict) tuples in document order."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))


def _parse_html_tags(html: str) -> list[tuple[str, dict[str, str | None]]]:
    collector = _TagCollector()
    collector.feed(html)
    return collector.tags


# ===================================================================
# Sub-task 1: Discover filterable fields from OpenAPI spec
# ===================================================================


class TestDiscoverFilterableFields:
    """app.js must have a discoverFilterFields function that processes the OpenAPI spec."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "discoverFilterFields")

    def test_discover_filter_fields_function_defined(self) -> None:
        """A function named discoverFilterFields must be defined in app.js."""
        assert self.fn_body is not None, (
            "Expected function discoverFilterFields(...) { ... } in app.js"
        )

    def test_constructs_api_path_key(self) -> None:
        """discoverFilterFields must build the /api/v1/{table} path key to look up
        the correct endpoint in the spec's paths object."""
        assert self.fn_body is not None
        assert '"/api/v1/"' in self.fn_body, (
            "discoverFilterFields must build path key using '/api/v1/' + table"
        )

    def test_reads_get_parameters(self) -> None:
        """Must read .get.parameters from the spec path object."""
        assert self.fn_body is not None
        assert ".get" in self.fn_body, (
            "discoverFilterFields must access .get on the path object"
        )
        assert "parameters" in self.fn_body, (
            "discoverFilterFields must read 'parameters' from the GET operation"
        )

    def test_filters_only_query_params(self) -> None:
        """Must only process params where in === 'query'."""
        assert self.fn_body is not None
        assert '"query"' in self.fn_body, (
            "discoverFilterFields must filter for in === 'query' parameters"
        )

    def test_excludes_page_and_per_page(self) -> None:
        """Must explicitly exclude 'page' and 'per_page' pagination params."""
        assert self.fn_body is not None
        assert '"page"' in self.fn_body and '"per_page"' in self.fn_body, (
            "discoverFilterFields must list 'page' and 'per_page' as excluded params"
        )

    def test_detects_after_suffix_for_date_range(self) -> None:
        """Must detect _after suffix to group date-range pairs."""
        assert self.fn_body is not None
        assert "_after" in self.fn_body, (
            "discoverFilterFields must detect '_after' suffix for date range grouping"
        )

    def test_detects_before_suffix_for_date_range(self) -> None:
        """Must detect _before suffix to group date-range pairs."""
        assert self.fn_body is not None
        assert "_before" in self.fn_body, (
            "discoverFilterFields must detect '_before' suffix for date range grouping"
        )

    def test_produces_date_range_kind(self) -> None:
        """Grouped date-range fields must be tagged with kind: 'date_range'."""
        assert self.fn_body is not None
        assert '"date_range"' in self.fn_body, (
            "discoverFilterFields must produce fields with kind: 'date_range'"
        )

    def test_checks_boolean_type(self) -> None:
        """Must detect boolean parameter type (including via anyOf for nullable)."""
        assert self.fn_body is not None
        assert '"boolean"' in self.fn_body, (
            "discoverFilterFields must detect boolean type from schema"
        )

    def test_returns_array_of_fields(self) -> None:
        """Must return an array (fields) of discovered filter field objects."""
        assert self.fn_body is not None
        assert "return fields" in self.fn_body or "return []" in self.fn_body, (
            "discoverFilterFields must return the fields array"
        )


# ===================================================================
# Sub-task 2: Render filter panel UI
# ===================================================================


class TestFilterPanelHTML:
    """table.html must have a <details id='filter-toggle'> element."""

    @pytest.fixture(autouse=True)
    def _load_html(self) -> None:
        self.html = _read_static("table.html")
        self.tags = _parse_html_tags(self.html)

    def test_filter_details_element_exists(self) -> None:
        """A <details id='filter-toggle'> element must exist in table.html."""
        details_ids = [
            attrs.get("id") for tag, attrs in self.tags if tag == "details"
        ]
        assert "filter-toggle" in details_ids, (
            "Expected <details id='filter-toggle'> in table.html"
        )

    def test_filter_details_has_summary(self) -> None:
        """The filter <details> must contain a <summary> with 'Filters' text."""
        # Find the summary text inside the filter details block
        summary_match = re.search(
            r'<details[^>]*id\s*=\s*["\']filter-toggle["\'][^>]*>\s*<summary>(.*?)</summary>',
            self.html,
            flags=re.DOTALL,
        )
        assert summary_match is not None, (
            "Expected <summary> inside <details id='filter-toggle'>"
        )
        assert "filter" in summary_match.group(1).lower(), (
            "Expected 'Filters' text in the filter panel summary"
        )

    def test_filter_inputs_container_exists(self) -> None:
        """A <div id='filter-inputs'> container must exist for dynamically rendered inputs."""
        div_ids = [attrs.get("id") for tag, attrs in self.tags if tag == "div"]
        assert "filter-inputs" in div_ids, (
            "Expected <div id='filter-inputs'> inside the filter panel"
        )

    def test_filter_panel_between_add_btn_and_table(self) -> None:
        """Filter panel must appear after add-record-btn and before the <table>."""
        add_btn_pos = self.html.find("add-record-btn")
        filter_pos = self.html.find('id="filter-toggle"')
        table_pos = self.html.find("<table")

        assert add_btn_pos != -1, "Expected add-record-btn in table.html"
        assert filter_pos != -1, "Expected filter-toggle in table.html"
        assert table_pos != -1, "Expected <table> in table.html"
        assert add_btn_pos < filter_pos < table_pos, (
            "Filter panel must appear after add-record-btn and before <table>"
        )

    def test_two_details_elements_exist(self) -> None:
        """Both Columns and Filters <details> must exist."""
        details_ids = [
            attrs.get("id") for tag, attrs in self.tags if tag == "details"
        ]
        assert "column-toggle" in details_ids, "Expected Columns <details>"
        assert "filter-toggle" in details_ids, "Expected Filters <details>"


class TestFilterPanelInputRendering:
    """app.js renderFilterPanel must create type-appropriate inputs."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "renderFilterPanel")

    def test_render_filter_panel_function_defined(self) -> None:
        """A renderFilterPanel function must be defined."""
        assert self.fn_body is not None, (
            "Expected function renderFilterPanel(...) { ... } in app.js"
        )

    def test_creates_text_input_for_string_fields(self) -> None:
        """Must create <input type='text'> for string/ILIKE fields."""
        assert self.fn_body is not None
        assert '"text"' in self.fn_body, (
            "renderFilterPanel must set input.type = 'text' for string fields"
        )

    def test_creates_select_for_boolean_fields(self) -> None:
        """Must create <select> element for boolean fields."""
        assert self.fn_body is not None
        assert 'createElement("select")' in self.fn_body, (
            "renderFilterPanel must createElement('select') for boolean fields"
        )

    def test_boolean_select_has_any_true_false_options(self) -> None:
        """Boolean <select> must have three options: 'Any' (empty), 'true', 'false'."""
        assert self.fn_body is not None
        assert '"Any"' in self.fn_body, "Expected 'Any' option in boolean select"
        assert '"true"' in self.fn_body, "Expected 'true' option in boolean select"
        assert '"false"' in self.fn_body, "Expected 'false' option in boolean select"

    def test_creates_datetime_local_for_date_range(self) -> None:
        """Must create <input type='datetime-local'> for date range fields."""
        assert self.fn_body is not None
        assert '"datetime-local"' in self.fn_body, (
            "renderFilterPanel must set input.type = 'datetime-local' for date ranges"
        )

    def test_date_range_has_after_and_before_labels(self) -> None:
        """DATE_RANGE inputs must have 'After' and 'Before' labels."""
        assert self.fn_body is not None
        assert '"After"' in self.fn_body, "Expected 'After' label for date range"
        assert '"Before"' in self.fn_body, "Expected 'Before' label for date range"

    def test_sets_data_filter_attribute(self) -> None:
        """Each input must have a data-filter attribute for param name identification."""
        assert self.fn_body is not None
        assert "data-filter" in self.fn_body, (
            "renderFilterPanel must set data-filter attribute on inputs"
        )

    def test_creates_apply_filters_button(self) -> None:
        """An 'Apply Filters' button must be created."""
        assert self.fn_body is not None
        assert '"Apply Filters"' in self.fn_body, (
            "renderFilterPanel must create an 'Apply Filters' button"
        )

    def test_creates_clear_button(self) -> None:
        """A 'Clear' button must be created."""
        assert self.fn_body is not None
        assert '"Clear"' in self.fn_body, (
            "renderFilterPanel must create a 'Clear' button"
        )

    def test_apply_button_calls_apply_filters(self) -> None:
        """Apply button click handler must call applyFilters()."""
        assert self.fn_body is not None
        assert "applyFilters()" in self.fn_body, (
            "Apply button must call applyFilters() on click"
        )

    def test_clear_button_calls_clear_filters(self) -> None:
        """Clear button click handler must call clearFilters()."""
        assert self.fn_body is not None
        assert "clearFilters()" in self.fn_body, (
            "Clear button must call clearFilters() on click"
        )


# ===================================================================
# Sub-task 3: Apply filters and refetch data
# ===================================================================


class TestApplyFilters:
    """applyFilters must collect inputs, build query params, and delegate to fetchAndRender."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "applyFilters")

    def test_apply_filters_function_defined(self) -> None:
        """applyFilters function must be defined."""
        assert self.fn_body is not None, (
            "Expected function applyFilters() { ... } in app.js"
        )

    def test_creates_url_search_params(self) -> None:
        """Must create a URLSearchParams to build query string."""
        assert self.fn_body is not None
        assert "URLSearchParams" in self.fn_body, (
            "applyFilters must use URLSearchParams to build query string"
        )

    def test_sets_page_to_one(self) -> None:
        """Must reset pagination to page 1."""
        assert self.fn_body is not None
        # Verify it explicitly appends page=1
        assert re.search(r'append\(\s*"page"\s*,\s*"1"\s*\)', self.fn_body), (
            "applyFilters must append page=1 to reset pagination"
        )

    def test_queries_data_filter_elements(self) -> None:
        """Must query all [data-filter] elements to collect filter values."""
        assert self.fn_body is not None
        assert "[data-filter]" in self.fn_body, (
            "applyFilters must select [data-filter] elements to read filter values"
        )

    def test_skips_empty_values(self) -> None:
        """Must check for non-empty values before appending to params."""
        assert self.fn_body is not None
        assert '!== ""' in self.fn_body, (
            "applyFilters must skip empty string values when building query params"
        )

    def test_delegates_to_fetch_and_render(self) -> None:
        """Must call fetchAndRender(params) instead of duplicating fetch logic."""
        assert self.fn_body is not None
        assert "fetchAndRender(params)" in self.fn_body, (
            "applyFilters must delegate to fetchAndRender(params) — "
            "no duplicated fetch/render logic"
        )


class TestFetchAndRender:
    """fetchAndRender is the shared helper used by both applyFilters and clearFilters."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "fetchAndRender")

    def test_fetch_and_render_function_defined(self) -> None:
        """fetchAndRender function must be defined to avoid code duplication."""
        assert self.fn_body is not None, (
            "Expected function fetchAndRender(params) { ... } in app.js — "
            "shared helper to eliminate duplication between applyFilters/clearFilters"
        )

    def test_fetches_api_endpoint(self) -> None:
        """Must fetch /api/v1/{table} with the given params."""
        assert self.fn_body is not None
        assert "fetch(" in self.fn_body, "fetchAndRender must call fetch()"
        assert "/api/v1/" in self.fn_body, "fetchAndRender must use /api/v1/ endpoint"

    def test_updates_table_state(self) -> None:
        """Must update TableState.originalItems and TableState.items."""
        assert self.fn_body is not None
        assert "TableState.originalItems" in self.fn_body, (
            "fetchAndRender must update TableState.originalItems"
        )
        assert "TableState.items" in self.fn_body, (
            "fetchAndRender must update TableState.items"
        )

    def test_calls_reapply_sort_not_sort_by_column(self) -> None:
        """Must call reapplySort() — NOT sortByColumn() — to avoid toggling sort direction.

        This is the key fix for the sort-direction bug: sortByColumn toggles the
        direction when called with the same column, which would silently reverse
        the sort on every filter apply/clear.
        """
        assert self.fn_body is not None
        assert "reapplySort()" in self.fn_body, (
            "fetchAndRender must call reapplySort() to preserve sort direction"
        )
        assert "sortByColumn(" not in self.fn_body, (
            "fetchAndRender must NOT call sortByColumn() — that toggles the sort direction"
        )

    def test_calls_render_table(self) -> None:
        """Must call renderTable to re-render when no sort is active."""
        assert self.fn_body is not None
        assert "renderTable(" in self.fn_body, (
            "fetchAndRender must call renderTable() when no sort column is active"
        )

    def test_handles_empty_results(self) -> None:
        """Must handle empty results (items.length === 0) gracefully."""
        assert self.fn_body is not None
        assert "items.length === 0" in self.fn_body or "items.length==0" in self.fn_body, (
            "fetchAndRender must handle empty result sets"
        )

    def test_shows_and_hides_loading_indicator(self) -> None:
        """Must show loading indicator before fetch and hide it after."""
        assert self.fn_body is not None
        assert "loading" in self.fn_body, (
            "fetchAndRender must manage loading indicator visibility"
        )

    def test_handles_fetch_errors(self) -> None:
        """Must catch fetch errors and call showError."""
        assert self.fn_body is not None
        assert "showError" in self.fn_body, (
            "fetchAndRender must call showError on fetch failure"
        )


class TestReapplySort:
    """reapplySort must re-sort data using current sort state WITHOUT toggling direction."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "reapplySort")

    def test_reapply_sort_function_defined(self) -> None:
        """reapplySort function must be defined to fix the sort-direction bug."""
        assert self.fn_body is not None, (
            "Expected function reapplySort() { ... } in app.js — "
            "sorts without toggling direction"
        )

    def test_reads_current_sort_column(self) -> None:
        """Must read TableState.sortColumn."""
        assert self.fn_body is not None
        assert "TableState.sortColumn" in self.fn_body, (
            "reapplySort must read the current sort column from TableState"
        )

    def test_reads_current_sort_direction(self) -> None:
        """Must use TableState.sortDirection for comparison."""
        assert self.fn_body is not None
        assert "TableState.sortDirection" in self.fn_body, (
            "reapplySort must use the current sort direction from TableState"
        )

    def test_does_not_toggle_direction(self) -> None:
        """Must NOT contain direction-toggle logic (the key difference from sortByColumn)."""
        assert self.fn_body is not None
        # sortByColumn toggles with: TableState.sortDirection = TableState.sortDirection === "asc" ? "desc" : "asc"
        # reapplySort must NOT reassign sortDirection — only read it for comparisons.
        # We check for assignment patterns (= without preceding =, !, <, >) to
        # distinguish from === comparisons.
        has_assignment = bool(
            re.search(r"TableState\.sortDirection\s*=[^=]", self.fn_body)
        )
        assert not has_assignment, (
            "reapplySort must NOT assign to TableState.sortDirection — "
            "it should preserve the current direction, not toggle it"
        )

    def test_sorts_original_items_copy(self) -> None:
        """Must sort a copy of originalItems (never mutate)."""
        assert self.fn_body is not None
        assert "TableState.originalItems.slice()" in self.fn_body, (
            "reapplySort must sort a .slice() copy of originalItems"
        )

    def test_calls_render_table(self) -> None:
        """Must call renderTable with the sorted items."""
        assert self.fn_body is not None
        assert "renderTable(" in self.fn_body, (
            "reapplySort must call renderTable to display the sorted data"
        )


class TestPreserveStateAfterFilter:
    """Column visibility and sort state must be preserved after filtering."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_table_state_has_filter_fields(self) -> None:
        """TableState must include filterFields to store discovered fields."""
        assert "filterFields" in self.js, (
            "TableState must have filterFields property"
        )

    def test_hidden_columns_not_cleared_on_filter(self) -> None:
        """fetchAndRender must not reset hiddenColumns."""
        fn_body = _extract_js_function_body(self.js, "fetchAndRender")
        assert fn_body is not None
        # It should never assign a new value to hiddenColumns
        assert "hiddenColumns = {}" not in fn_body, (
            "fetchAndRender must not reset hiddenColumns — they must persist"
        )

    def test_sort_preserved_via_reapply_sort(self) -> None:
        """fetchAndRender must use reapplySort() to re-apply sort without toggling."""
        fn_body = _extract_js_function_body(self.js, "fetchAndRender")
        assert fn_body is not None
        assert "reapplySort()" in fn_body, (
            "fetchAndRender must call reapplySort() to preserve sort direction"
        )


# ===================================================================
# Sub-task 4: Clear filters
# ===================================================================


class TestClearFilters:
    """clearFilters must reset inputs and delegate to fetchAndRender."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.fn_body = _extract_js_function_body(self.js, "clearFilters")

    def test_clear_filters_function_defined(self) -> None:
        """clearFilters function must be defined."""
        assert self.fn_body is not None, (
            "Expected function clearFilters() { ... } in app.js"
        )

    def test_resets_select_elements(self) -> None:
        """Must reset <select> elements via selectedIndex = 0."""
        assert self.fn_body is not None
        assert "selectedIndex" in self.fn_body, (
            "clearFilters must reset <select> elements via selectedIndex = 0"
        )

    def test_resets_input_values(self) -> None:
        """Must reset <input> values to empty string."""
        assert self.fn_body is not None
        assert '.value = ""' in self.fn_body or ".value = ''" in self.fn_body, (
            "clearFilters must reset input values to empty string"
        )

    def test_delegates_to_fetch_and_render(self) -> None:
        """Must call fetchAndRender(params) instead of duplicating fetch logic."""
        assert self.fn_body is not None
        assert "fetchAndRender(params)" in self.fn_body, (
            "clearFilters must delegate to fetchAndRender(params) — "
            "no duplicated fetch/render logic"
        )

    def test_does_not_duplicate_fetch_logic(self) -> None:
        """clearFilters must NOT contain its own fetch() call."""
        assert self.fn_body is not None
        assert "fetch(" not in self.fn_body, (
            "clearFilters must not call fetch() directly — "
            "it should use fetchAndRender() to avoid code duplication"
        )


# ===================================================================
# Code quality: no duplication between applyFilters / clearFilters
# ===================================================================


class TestNoDuplicatedFetchLogic:
    """applyFilters and clearFilters must both delegate to fetchAndRender,
    not duplicate the fetch → parse → sort → render pipeline."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.apply_body = _extract_js_function_body(self.js, "applyFilters")
        self.clear_body = _extract_js_function_body(self.js, "clearFilters")
        self.fetch_render_body = _extract_js_function_body(self.js, "fetchAndRender")

    def test_fetch_and_render_exists(self) -> None:
        """A shared fetchAndRender function must exist."""
        assert self.fetch_render_body is not None, (
            "fetchAndRender must exist as a shared helper"
        )

    def test_apply_filters_has_no_fetch(self) -> None:
        """applyFilters must not contain its own fetch() call."""
        assert self.apply_body is not None
        assert "fetch(" not in self.apply_body, (
            "applyFilters should delegate to fetchAndRender, not call fetch() directly"
        )

    def test_clear_filters_has_no_fetch(self) -> None:
        """clearFilters must not contain its own fetch() call."""
        assert self.clear_body is not None
        assert "fetch(" not in self.clear_body, (
            "clearFilters should delegate to fetchAndRender, not call fetch() directly"
        )

    def test_apply_filters_calls_fetch_and_render(self) -> None:
        """applyFilters must call fetchAndRender."""
        assert self.apply_body is not None
        assert "fetchAndRender(" in self.apply_body

    def test_clear_filters_calls_fetch_and_render(self) -> None:
        """clearFilters must call fetchAndRender."""
        assert self.clear_body is not None
        assert "fetchAndRender(" in self.clear_body


# ===================================================================
# Filter panel CSS
# ===================================================================


class TestFilterPanelCSS:
    """Filter panel should be styled consistently with existing UI."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_filter_toggle_has_styling(self) -> None:
        """#filter-toggle must have CSS rules."""
        blocks = _find_blocks(self.css, "#filter-toggle")
        assert len(blocks) > 0, "Expected CSS rules for #filter-toggle"

    def test_filter_inputs_has_styling(self) -> None:
        """#filter-inputs must have CSS rules."""
        blocks = _find_blocks(self.css, "#filter-inputs")
        assert len(blocks) > 0, "Expected CSS rules for #filter-inputs"

    def test_filter_buttons_has_styling(self) -> None:
        """.filter-buttons must have CSS rules for button layout."""
        blocks = _find_blocks(self.css, ".filter-buttons")
        assert len(blocks) > 0, "Expected CSS rules for .filter-buttons"

    def test_btn_secondary_exists(self) -> None:
        """.btn-secondary must exist for the Clear button."""
        blocks = _find_blocks(self.css, ".btn-secondary")
        assert len(blocks) > 0, "Expected .btn-secondary CSS for Clear button"

    def test_select_input_styled(self) -> None:
        """<select> elements in filter panel must be styled."""
        blocks = _find_blocks(self.css, "select")
        assert len(blocks) > 0, "Expected CSS rules for select elements"


# ===================================================================
# Acceptance criteria: integration-level checks
# ===================================================================


class TestFilterPanelAcceptanceCriteria:
    """Cross-cutting acceptance criteria checks across all static files."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.js = _read_static("app.js")
        self.html = _read_static("table.html")
        self.css = _read_static("style.css")

    def test_filter_panel_is_collapsible_details(self) -> None:
        """AC: Filter panel appears as collapsible <details id='filter-toggle'> on table page."""
        assert re.search(
            r'<details[^>]*id\s*=\s*["\']filter-toggle["\']', self.html
        ), "Expected <details id='filter-toggle'> in table.html"

    def test_inputs_match_field_types(self) -> None:
        """AC: renderFilterPanel creates text, select, and datetime-local inputs."""
        fn_body = _extract_js_function_body(self.js, "renderFilterPanel")
        assert fn_body is not None
        assert '"text"' in fn_body, "AC: Expected text input type"
        assert 'createElement("select")' in fn_body, "AC: Expected select element"
        assert '"datetime-local"' in fn_body, "AC: Expected datetime-local input"

    def test_apply_sends_query_params_and_rerenders(self) -> None:
        """AC: applyFilters builds query params and delegates to fetchAndRender."""
        apply_body = _extract_js_function_body(self.js, "applyFilters")
        assert apply_body is not None
        assert "URLSearchParams" in apply_body, "AC: Expected URL param construction"
        assert "fetchAndRender(" in apply_body, "AC: Expected fetchAndRender call"

    def test_clear_resets_and_refetches(self) -> None:
        """AC: clearFilters resets inputs and delegates to fetchAndRender."""
        clear_body = _extract_js_function_body(self.js, "clearFilters")
        assert clear_body is not None
        assert "selectedIndex" in clear_body or '.value = ""' in clear_body, (
            "AC: Expected input reset logic"
        )
        assert "fetchAndRender(" in clear_body, "AC: Expected fetchAndRender call"

    def test_column_visibility_preserved(self) -> None:
        """AC: hiddenColumns state is not reset by fetchAndRender."""
        fn_body = _extract_js_function_body(self.js, "fetchAndRender")
        assert fn_body is not None
        assert "hiddenColumns" not in fn_body or "hiddenColumns = {}" not in fn_body, (
            "AC: fetchAndRender must not reset hiddenColumns"
        )

    def test_sorting_preserved_via_reapply_sort(self) -> None:
        """AC: Sort is preserved by reapplySort() (not sortByColumn toggle)."""
        fn_body = _extract_js_function_body(self.js, "fetchAndRender")
        assert fn_body is not None
        assert "reapplySort()" in fn_body, (
            "AC: fetchAndRender must call reapplySort to preserve sort direction"
        )
        assert "sortByColumn(" not in fn_body, (
            "AC: fetchAndRender must NOT call sortByColumn (it toggles direction)"
        )

    def test_pagination_resets_to_page_one(self) -> None:
        """AC: applyFilters resets pagination to page 1."""
        apply_body = _extract_js_function_body(self.js, "applyFilters")
        assert apply_body is not None
        assert re.search(r'append\(\s*"page"\s*,\s*"1"\s*\)', apply_body), (
            "AC: applyFilters must set page=1"
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
        self.fn_names = _js_function_names(self.js)

    def test_tables_array_still_defined(self) -> None:
        """TABLES constant must still exist."""
        assert "TABLES" in self.js

    def test_table_state_has_required_properties(self) -> None:
        """TableState object must still have all original + new properties."""
        for prop in ["sortColumn", "sortDirection", "headers", "originalItems",
                      "items", "hiddenColumns", "filterFields"]:
            assert prop in self.js, f"TableState must have '{prop}' property"

    def test_required_functions_exist(self) -> None:
        """All required functions must be defined in app.js."""
        required = [
            "escapeHtml", "discoverFilterFields", "renderFilterPanel",
            "fetchAndRender", "reapplySort", "applyFilters", "clearFilters",
            "initTablePage", "renderTable", "sortByColumn",
            "renderColumnToggles", "toggleColumnVisibility", "showError",
            "initEditPage", "initCreatePage", "discoverCreateFields",
            "resolveRef",
        ]
        for name in required:
            assert name in self.fn_names, f"Function '{name}' must exist in app.js"

    def test_column_toggle_details_preserved(self) -> None:
        """Original Columns <details id='column-toggle'> must still exist."""
        assert "column-toggle" in self.html

    def test_column_checkboxes_container_preserved(self) -> None:
        """Original column-checkboxes div must still exist."""
        assert "column-checkboxes" in self.html

    def test_loading_and_error_elements_still_in_html(self) -> None:
        """Loading and error display elements must still be in table.html."""
        assert 'id="loading"' in self.html
        assert 'id="error"' in self.html

    def test_data_table_element_still_in_html(self) -> None:
        """data-table, table-head, and table-body must still exist."""
        assert "data-table" in self.html
        assert "table-head" in self.html
        assert "table-body" in self.html

    def test_add_record_btn_still_in_html(self) -> None:
        """Add Record button must still exist."""
        assert "add-record-btn" in self.html

    def test_style_and_script_links_preserved(self) -> None:
        """table.html must still link to style.css and app.js."""
        assert "style.css" in self.html
        assert "app.js" in self.html

    def test_col_hidden_class_still_exists(self) -> None:
        """style.css must still define .col-hidden."""
        col_hidden_blocks = _find_blocks(self.css, "col-hidden")
        assert len(col_hidden_blocks) > 0, "Expected .col-hidden CSS"

    def test_sortable_header_class_still_exists(self) -> None:
        """style.css must still define .sortable-header."""
        sortable_blocks = _find_blocks(self.css, "sortable-header")
        assert len(sortable_blocks) > 0, "Expected .sortable-header CSS"

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
        assert has_pointer, "Expected cursor: pointer on 'tbody tr'"


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
