"""Tests for PR #36 review fixes.

Covers the issues raised in the code review:
  1. XSS: HTML-escape cell values and header names before innerHTML injection
  2. Sort mutation: sortByColumn must not mutate the original items array
  3. CSS scoping: cursor:pointer should target .sortable-header, not bare th
  4. State encapsulation: module-level globals should be encapsulated in an object
  5. Row navigation guard: row clicks should be guarded since edit.html doesn't exist
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
# Issue 1: XSS — HTML-escape cell values and header names
# ===================================================================


class TestXSSEscaping:
    """Cell values and header names must be HTML-escaped before innerHTML injection."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_escape_html_function_exists(self) -> None:
        """app.js must define an escapeHtml (or equivalent) helper function.

        This function should replace &, <, >, ", ' with HTML entities.
        """
        has_escape_fn = any(
            token in self.js
            for token in [
                "escapeHtml",
                "escapeHTML",
                "htmlEscape",
                "sanitizeHtml",
            ]
        )
        assert has_escape_fn, (
            "Expected an HTML escape function (escapeHtml or equivalent) in app.js "
            "to prevent XSS from unsanitized data"
        )

    def test_escape_replaces_ampersand(self) -> None:
        """The escape function must replace & with &amp;."""
        assert "&amp;" in self.js or "\\x26amp;" in self.js, (
            "Expected &amp; replacement in escape function"
        )

    def test_escape_replaces_less_than(self) -> None:
        """The escape function must replace < with &lt;."""
        assert "&lt;" in self.js or "\\x26lt;" in self.js, (
            "Expected &lt; replacement in escape function"
        )

    def test_escape_replaces_greater_than(self) -> None:
        """The escape function must replace > with &gt;."""
        assert "&gt;" in self.js or "\\x26gt;" in self.js, (
            "Expected &gt; replacement in escape function"
        )

    def test_escape_replaces_double_quote(self) -> None:
        """The escape function must replace " with &quot;."""
        assert "&quot;" in self.js or "\\x26quot;" in self.js or "&#34;" in self.js, (
            "Expected &quot; replacement in escape function"
        )

    def test_escape_replaces_single_quote(self) -> None:
        """The escape function must replace ' with &#39; or &apos;."""
        has_single_quote_escape = any(
            token in self.js
            for token in ["&#39;", "&apos;", "&#x27;", "\\x27"]
        )
        assert has_single_quote_escape, (
            "Expected single-quote escape (&#39; or &apos;) in escape function"
        )

    def test_cell_values_are_escaped(self) -> None:
        """Cell values must be passed through the escape function before
        being interpolated into the HTML string in renderTable().
        """
        # Look for the pattern where val is escaped before insertion into <td>
        # e.g., escapeHtml(val) or equivalent
        has_escaped_val = any(
            token in self.js
            for token in [
                "escapeHtml(val",
                "escapeHTML(val",
                "htmlEscape(val",
                "escapeHtml(String(val",
            ]
        )
        assert has_escaped_val, (
            "Expected cell values to be passed through escapeHtml() before "
            "interpolation into innerHTML"
        )

    def test_header_names_are_escaped(self) -> None:
        """Header names (from API response keys) must also be escaped.

        The reviewer noted that headers[i] is interpolated without escaping
        in the <th> construction.
        """
        has_escaped_header = any(
            token in self.js
            for token in [
                "escapeHtml(headers[",
                "escapeHTML(headers[",
                "htmlEscape(headers[",
                "escapeHtml(header",
            ]
        )
        assert has_escaped_header, (
            "Expected header names to be passed through escapeHtml() before "
            "interpolation into innerHTML"
        )


# ===================================================================
# Issue 2: Sort mutation — must not mutate original items array
# ===================================================================


class TestSortImmutability:
    """sortByColumn must sort a copy, not mutate the shared currentItems array."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_original_items_preserved(self) -> None:
        """The code must store the original items separately so the original
        order can be restored (e.g., originalItems, _originalItems, etc.).
        """
        has_original = any(
            token in self.js
            for token in [
                "originalItems",
                "_originalItems",
                "unsortedItems",
                "originalOrder",
            ]
        )
        assert has_original, (
            "Expected a separate variable to store original items order "
            "(e.g., originalItems) so the original server order is preserved"
        )

    def test_sort_uses_copy_not_in_place(self) -> None:
        """sortByColumn must sort a shallow copy, not currentItems directly.

        The fix should use [...arr].sort() or arr.slice().sort() pattern.
        """
        # The sort should NOT be called directly on currentItems
        # Look for copy patterns: slice().sort(), [... ].sort(), concat().sort()
        has_copy_sort = any(
            token in self.js
            for token in [
                ".slice().sort(",
                ".slice()",
                "[...current",
                "[...original",
                "concat().sort(",
                "Array.from(",
            ]
        )
        assert has_copy_sort, (
            "Expected sort to operate on a copy ([...items].sort() or "
            "items.slice().sort()) not on the original array in-place"
        )

    def test_sort_does_not_directly_mutate_original(self) -> None:
        """The pattern 'originalItems.sort(' must NOT appear — the original
        array must never be sorted.
        """
        assert "originalItems.sort(" not in self.js, (
            "originalItems must never be sorted — only copies should be sorted"
        )


# ===================================================================
# Issue 3: CSS scoping — cursor:pointer on .sortable-header not bare th
# ===================================================================


class TestCSSCursorScoping:
    """cursor: pointer must be scoped to sortable headers, not all <th>."""

    @pytest.fixture(autouse=True)
    def _load_css(self) -> None:
        self.css = _read_static("style.css")

    def test_bare_th_no_cursor_pointer(self) -> None:
        """The bare 'th' rule must NOT have cursor: pointer.

        The reviewer noted this is too broad and affects all tables on all pages.
        """
        blocks = _css_blocks(self.css)
        for selector, body in blocks:
            # Match bare 'th' selector (not 'th.something' or '#x th')
            if selector.strip() == "th":
                assert not _css_has_property(body, "cursor", "pointer"), (
                    "Bare 'th' selector must NOT have cursor: pointer — "
                    "it should be scoped to .sortable-header or #data-table th"
                )

    def test_sortable_header_or_scoped_th_has_cursor_pointer(self) -> None:
        """cursor: pointer must be on a scoped selector like .sortable-header
        or #data-table th.
        """
        has_scoped_pointer = False
        for selector, body in _css_blocks(self.css):
            if _css_has_property(body, "cursor", "pointer"):
                if any(
                    scope in selector
                    for scope in [
                        ".sortable-header",
                        "#data-table th",
                        ".sortable",
                        "data-table",
                    ]
                ):
                    has_scoped_pointer = True
                    break
        assert has_scoped_pointer, (
            "Expected cursor: pointer on a scoped selector like .sortable-header "
            "or #data-table th, not on bare 'th'"
        )


# ===================================================================
# Issue 4: State encapsulation — globals into object/closure
# ===================================================================


class TestStateEncapsulation:
    """Module-level mutable globals should be encapsulated in an object or closure."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_state_object_exists(self) -> None:
        """State should be encapsulated in a named object (e.g., TableState, state, etc.).

        The reviewer flagged 6 bare 'var' globals at module level as fragile.
        """
        has_state_object = any(
            token in self.js
            for token in [
                "TableState",
                "tableState",
                "var state =",
                "var state=",
                "const state =",
                "const state=",
                "let state =",
            ]
        )
        assert has_state_object, (
            "Expected state variables to be encapsulated in an object "
            "(e.g., var TableState = {...} or var state = {...})"
        )

    def test_no_bare_global_sort_vars(self) -> None:
        """Bare 'var currentSortColumn' at module level should no longer exist.

        These should be properties on a state object instead.
        """
        # Split into lines and check for bare global var declarations
        lines = self.js.split("\n")
        bare_globals = [
            line.strip()
            for line in lines
            if re.match(r"^var\s+current(SortColumn|SortDirection|Headers|Items|Table)\s*=", line.strip())
        ]
        assert len(bare_globals) == 0, (
            f"Found bare global var declarations that should be in state object: "
            f"{bare_globals}"
        )


# ===================================================================
# Issue 5: Row navigation guard — edit.html doesn't exist
# ===================================================================


class TestRowNavigationGuard:
    """Row click navigation should be guarded since edit.html doesn't exist yet."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_row_click_is_guarded_or_disabled(self) -> None:
        """The row click handler should be guarded or disabled.

        Since edit.html doesn't exist, clicking a row should not navigate
        to a 404. Options:
        - Log/console.log instead of navigating
        - Check if edit page exists before navigating
        - Comment out or disable navigation
        - Show alert/message that edit is not yet available
        """
        has_guard = any(
            token in self.js
            for token in [
                "console.log",
                "console.warn",
                "alert(",
                "TODO",
                "not yet",
                "not available",
                "disabled",
                "// location.href",
                "/* location.href",
            ]
        )
        # Also accept if edit.html navigation was removed entirely
        has_no_edit_nav = "edit.html" not in self.js
        assert has_guard or has_no_edit_nav, (
            "Row click navigation to edit.html must be guarded or disabled "
            "since edit.html does not exist — clicking should not cause a 404"
        )

    def test_no_unguarded_edit_navigation(self) -> None:
        """If edit.html reference exists, it must be commented out or guarded."""
        if "edit.html" in self.js:
            # If edit.html is still referenced, it must be in a commented-out
            # or guarded context
            lines = self.js.split("\n")
            edit_lines = [
                line.strip()
                for line in lines
                if "edit.html" in line and not line.strip().startswith("//") and not line.strip().startswith("/*")
            ]
            # All active edit.html references should have a guard
            for line in edit_lines:
                has_guard = any(
                    g in line or g in self.js
                    for g in ["console.", "alert", "disabled", "TODO"]
                )
                assert has_guard or "location.href" not in line, (
                    f"Unguarded edit.html navigation found: {line!r}. "
                    "Must be commented out or guarded until edit.html exists."
                )


# ===================================================================
# Regression: Existing functionality must still work
# ===================================================================


class TestExistingFeaturesPreserved:
    """Ensure the fixes don't break existing table enhancement features."""

    @pytest.fixture(autouse=True)
    def _load_files(self) -> None:
        self.js = _read_static("app.js")
        self.css = _read_static("style.css")

    def test_sort_function_still_exists(self) -> None:
        """sortByColumn function must still exist."""
        assert "sortByColumn" in self.js

    def test_render_table_still_exists(self) -> None:
        """renderTable function must still exist."""
        assert "renderTable" in self.js

    def test_render_column_toggles_still_exists(self) -> None:
        """renderColumnToggles function must still exist."""
        assert "renderColumnToggles" in self.js

    def test_toggle_column_visibility_still_exists(self) -> None:
        """toggleColumnVisibility function must still exist."""
        assert "toggleColumnVisibility" in self.js

    def test_col_hidden_css_still_exists(self) -> None:
        """.col-hidden CSS rule must still exist."""
        blocks = _find_blocks(self.css, "col-hidden")
        assert len(blocks) > 0

    def test_tbody_tr_still_has_cursor_pointer(self) -> None:
        """tbody tr must still have cursor: pointer for row clickability."""
        # Exclude hover and nth-child rules, keep only plain tbody tr rules
        non_hover = [b for s, b in _css_blocks(self.css) if "tbody tr" in s and "hover" not in s and "nth" not in s]
        has_pointer = any(
            _css_has_property(body, "cursor", "pointer")
            for body in non_hover
        )
        assert has_pointer, "tbody tr must still have cursor: pointer"

    def test_sort_indicators_still_present(self) -> None:
        """Sort indicator arrows must still be in the code."""
        # The JS file may use \\u25B2 escape sequences or literal ▲/▼ chars
        has_up = "\\u25B2" in self.js or "\u25B2" in self.js or "&#9650" in self.js
        has_down = "\\u25BC" in self.js or "\u25BC" in self.js or "&#9660" in self.js
        assert has_up, "Expected ascending sort indicator (▲ or \\u25B2) in app.js"
        assert has_down, "Expected descending sort indicator (▼ or \\u25BC) in app.js"
