"""Tests for the edit page bug described in spec.txt.

Bug: edit.html renders only the title because app.js has two initEditPage()
declarations. The empty placeholder at line 489 overwrites the full
implementation at line 223 due to JavaScript function hoisting.

Fix requirements:
  1. Delete the empty initEditPage() placeholder (lines 489-491)
  2. Delete the duplicate else-if edit-form check (lines 36-38)
  3. Verify edit page loads fields and submits PUT requests correctly
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

STATIC_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "jm_api" / "static"


def _read_static(filename: str) -> str:
    """Read a static file's text content from disk."""
    path = STATIC_DIR / filename
    assert path.exists(), f"Expected static file not found: {path}"
    return path.read_text()


def _walk_braces(js: str, open_pos: int) -> str:
    """Extract a brace-delimited body starting after the opening '{' at open_pos.

    Returns the text *between* the braces (exclusive).
    """
    depth = 1
    pos = open_pos + 1
    while pos < len(js) and depth > 0:
        if js[pos] == "{":
            depth += 1
        elif js[pos] == "}":
            depth -= 1
        pos += 1
    return js[open_pos + 1 : pos - 1]


def _extract_function_body(js: str, fn_name: str) -> str | None:
    """Extract the full body of a named JS function using brace-walking."""
    m = re.search(rf"function\s+{fn_name}\s*\([^)]*\)\s*\{{", js)
    if not m:
        return None
    return _walk_braces(js, m.end() - 1)


def _extract_dcl_handler_body(js: str) -> str:
    """Extract the DOMContentLoaded callback body using brace-walking."""
    dcl_match = re.search(
        r'addEventListener\s*\(\s*["\']DOMContentLoaded["\']', js,
    )
    assert dcl_match, "DOMContentLoaded handler not found in app.js"
    brace_pos = js.index("{", dcl_match.start())
    return _walk_braces(js, brace_pos)


# ===================================================================
# Fix 1: No duplicate initEditPage() — empty placeholder must be gone
# ===================================================================


class TestNoDuplicateInitEditPage:
    """The empty initEditPage() placeholder must be removed.

    JavaScript function hoisting means when two function declarations have
    the same name, the LAST one wins. The empty placeholder at the end of
    app.js overwrites the full implementation, breaking the edit page.
    """

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_exactly_one_init_edit_page_declaration(self) -> None:
        """app.js must contain exactly ONE initEditPage function declaration."""
        # Match 'function initEditPage' at the start of a line (top-level declarations)
        declarations = re.findall(r"^\s*function\s+initEditPage\s*\(", self.js, re.MULTILINE)
        assert len(declarations) == 1, (
            f"Expected exactly 1 initEditPage declaration, found {len(declarations)}. "
            "The empty placeholder must be deleted."
        )

    def test_no_empty_init_edit_page(self) -> None:
        """There must be no empty/placeholder initEditPage function body.

        The placeholder is identified by a function body that contains only
        a comment and/or whitespace — no real statements.
        """
        # Use brace-walking to extract the full function body (handles nested braces)
        body = _extract_function_body(self.js, "initEditPage")
        assert body is not None, "initEditPage function not found"
        stripped = body.strip()
        # Remove single-line comments
        stripped = re.sub(r"//.*", "", stripped).strip()
        # Remove multi-line comments
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL).strip()
        assert stripped != "", (
            "Found an empty initEditPage placeholder (body has only comments/whitespace). "
            "This must be deleted — it overwrites the full implementation via hoisting."
        )

    def test_init_edit_page_has_fetch_logic(self) -> None:
        """The surviving initEditPage must contain fetch logic for loading the record."""
        body = _extract_function_body(self.js, "initEditPage")
        assert body is not None, "initEditPage function not found"

        assert "fetch" in body, (
            "initEditPage must contain fetch() call to load the record data"
        )
        assert "table" in body and "id" in body, (
            "initEditPage must read table and id from URL parameters"
        )

    def test_no_placeholder_comment(self) -> None:
        """The 'Placeholder for edit page initialization' comment should be gone."""
        assert "Placeholder for edit page initialization" not in self.js, (
            "The placeholder comment must be removed along with the empty function"
        )


# ===================================================================
# Fix 2: No duplicate edit-form branch in DOMContentLoaded
# ===================================================================


class TestNoDuplicateEditFormBranch:
    """The duplicate else-if edit-form check in DOMContentLoaded must be removed.

    Lines 32 and 36 both check for document.getElementById('edit-form').
    The second is dead code (unreachable) and must be deleted.
    """

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_edit_form_checked_exactly_once_in_dom_content_loaded(self) -> None:
        """The DOMContentLoaded handler must check for 'edit-form' exactly once."""
        handler_body = _extract_dcl_handler_body(self.js)

        edit_form_checks = re.findall(
            r'getElementById\s*\(\s*["\']edit-form["\']\s*\)', handler_body
        )
        assert len(edit_form_checks) == 1, (
            f"Expected exactly 1 edit-form check in DOMContentLoaded, "
            f"found {len(edit_form_checks)}. The duplicate else-if block "
            "is dead code and must be removed."
        )

    def test_init_edit_page_called_once_in_handler(self) -> None:
        """initEditPage() must appear exactly once in the DOMContentLoaded handler."""
        handler_body = _extract_dcl_handler_body(self.js)

        calls = re.findall(r"initEditPage\s*\(\s*\)", handler_body)
        assert len(calls) == 1, (
            f"Expected exactly 1 initEditPage() call in DOMContentLoaded, "
            f"found {len(calls)}."
        )

    def test_no_unreachable_else_if_after_create_form(self) -> None:
        """The else-if chain must not have an edit-form check AFTER create-form.

        Correct order: data-table → edit-form → create-form.
        An edit-form check after create-form is unreachable dead code.
        """
        handler_body = _extract_dcl_handler_body(self.js)

        # Find positions of create-form and edit-form checks
        create_positions = [
            m.start()
            for m in re.finditer(r'getElementById\s*\(\s*["\']create-form["\']\s*\)', handler_body)
        ]
        edit_positions = [
            m.start()
            for m in re.finditer(r'getElementById\s*\(\s*["\']edit-form["\']\s*\)', handler_body)
        ]

        if create_positions and edit_positions:
            # No edit-form check should appear AFTER the create-form check
            last_create = max(create_positions)
            edit_after_create = [p for p in edit_positions if p > last_create]
            assert len(edit_after_create) == 0, (
                "Found edit-form check after create-form check — this is "
                "unreachable dead code and must be removed."
            )


# ===================================================================
# Fix 3: Edit page loads fields and submits PUT correctly
# ===================================================================


class TestEditPageFunctionality:
    """Verify the full initEditPage implementation is the one that runs.

    After fix, the real initEditPage must:
      - Read table and id from URL params
      - Fetch record data and OpenAPI schema
      - Call renderEditForm to build the form
      - Submit PUT requests on save

    Assertions use regex to tolerate quote-style and whitespace variations.
    """

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")
        self.edit_body = _extract_function_body(self.js, "initEditPage")
        self.submit_body = _extract_function_body(self.js, "submitEditForm")

    def test_init_edit_page_reads_url_params(self) -> None:
        """initEditPage must parse table and id from URL search params."""
        assert self.edit_body is not None, "initEditPage not found"
        assert "URLSearchParams" in self.edit_body
        assert re.search(r"get\s*\(\s*[\"']table[\"']\s*\)", self.edit_body), (
            "initEditPage must read 'table' from URL search params"
        )
        assert re.search(r"get\s*\(\s*[\"']id[\"']\s*\)", self.edit_body), (
            "initEditPage must read 'id' from URL search params"
        )

    def test_init_edit_page_fetches_record(self) -> None:
        """initEditPage must fetch the individual record via /api/v1/{table}/{id}."""
        assert self.edit_body is not None, "initEditPage not found"
        assert re.search(r"/api/v1/", self.edit_body), (
            "initEditPage must fetch the record at /api/v1/{table}/{id}"
        )
        assert "fetch" in self.edit_body, (
            "initEditPage must use fetch() to retrieve the record"
        )

    def test_init_edit_page_fetches_openapi_schema(self) -> None:
        """initEditPage must fetch /openapi.json to discover editable fields."""
        assert self.edit_body is not None, "initEditPage not found"
        assert re.search(r"[\"'`]/openapi\.json[\"'`]", self.edit_body), (
            "initEditPage must fetch OpenAPI schema to discover form fields"
        )

    def test_init_edit_page_calls_render_edit_form(self) -> None:
        """initEditPage must call renderEditForm to build the edit form."""
        assert self.edit_body is not None, "initEditPage not found"
        assert re.search(r"renderEditForm\s*\(", self.edit_body), (
            "initEditPage must call renderEditForm to populate the edit form"
        )

    def test_submit_edit_form_uses_put(self) -> None:
        """submitEditForm must send a PUT request to update the record."""
        assert self.submit_body is not None, "submitEditForm not found"
        assert re.search(r"method\s*:\s*[\"']PUT[\"']", self.submit_body), (
            "submitEditForm must use HTTP PUT method to update the record"
        )

    def test_submit_edit_form_sends_json(self) -> None:
        """submitEditForm must send JSON body with Content-Type header."""
        assert self.submit_body is not None, "submitEditForm not found"
        assert re.search(
            r"[\"']Content-Type[\"']\s*:\s*[\"']application/json[\"']",
            self.submit_body,
        ), "submitEditForm must set Content-Type: application/json header"

    def test_submit_edit_form_redirects_on_success(self) -> None:
        """submitEditForm must redirect to table page on success."""
        assert self.submit_body is not None, "submitEditForm not found"
        assert "table.html" in self.submit_body, (
            "submitEditForm must redirect to table.html after successful update"
        )

    def test_submit_edit_form_shows_error_on_failure(self) -> None:
        """submitEditForm must show error message on failure."""
        assert self.submit_body is not None, "submitEditForm not found"
        assert "showError" in self.submit_body, (
            "submitEditForm must call showError on failed update"
        )


# ===================================================================
# Integration: PUT /api/v1/bots/{id} round-trip after fix
# ===================================================================


class TestEditApiRoundTrip:
    """After the fix, the edit page should work end-to-end.

    These tests verify the API endpoints that the fixed JS code calls.
    """

    def test_get_individual_bot(self, client: TestClient, bot_factory) -> None:
        """GET /api/v1/bots/{id} must return the bot record."""
        bot = bot_factory(rig_id="rig-get-test")
        resp = client.get(f"/api/v1/bots/{bot.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rig_id"] == "rig-get-test"

    def test_put_updates_bot(self, client: TestClient, bot_factory) -> None:
        """PUT /api/v1/bots/{id} must update and return the updated record."""
        bot = bot_factory(rig_id="rig-put-test", kill_switch=False)
        resp = client.put(
            f"/api/v1/bots/{bot.id}",
            json={"rig_id": "rig-updated", "kill_switch": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rig_id"] == "rig-updated"
        assert data["kill_switch"] is True

    def test_put_then_get_consistency(self, client: TestClient, bot_factory) -> None:
        """PUT followed by GET must return consistent data."""
        bot = bot_factory(rig_id="rig-consistency")
        put_resp = client.put(
            f"/api/v1/bots/{bot.id}",
            json={"rig_id": "rig-after-edit"},
        )
        assert put_resp.status_code == 200, (
            f"PUT failed with status {put_resp.status_code}: {put_resp.text}"
        )
        get_resp = client.get(f"/api/v1/bots/{bot.id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["rig_id"] == "rig-after-edit"

    def test_openapi_schema_available(self, client: TestClient) -> None:
        """GET /openapi.json must be available (needed by initEditPage)."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert "paths" in spec
        assert "/api/v1/bots" in spec["paths"]

    def test_openapi_has_post_schema_for_field_discovery(self, client: TestClient) -> None:
        """OpenAPI spec must have a POST schema for bots with requestBody.

        initEditPage uses discoverCreateFields which reads the POST schema.
        """
        resp = client.get("/openapi.json")
        spec = resp.json()
        bots_path = spec["paths"].get("/api/v1/bots", {})
        assert "post" in bots_path, "POST endpoint must exist for field discovery"
        assert "requestBody" in bots_path["post"], (
            "POST schema must have requestBody for discoverCreateFields"
        )

    def test_edit_html_served(self, client: TestClient) -> None:
        """GET /admin/edit.html must return 200 with HTML content."""
        resp = client.get("/admin/edit.html")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


# ===================================================================
# Regression: Core functions must still exist and be correct
# ===================================================================


class TestRegressionAfterFix:
    """Ensure the fix does not break other functionality."""

    @pytest.fixture(autouse=True)
    def _load_js(self) -> None:
        self.js = _read_static("app.js")

    def test_init_table_page_still_exists(self) -> None:
        """initTablePage must not be affected by the fix."""
        assert "function initTablePage" in self.js

    def test_init_create_page_still_exists(self) -> None:
        """initCreatePage must not be affected by the fix."""
        assert "function initCreatePage" in self.js

    def test_render_edit_form_still_exists(self) -> None:
        """renderEditForm must still exist."""
        assert "function renderEditForm" in self.js

    def test_submit_edit_form_still_exists(self) -> None:
        """submitEditForm must still exist."""
        assert "function submitEditForm" in self.js

    def test_discover_create_fields_still_exists(self) -> None:
        """discoverCreateFields must still exist (used by both create and edit pages)."""
        assert "function discoverCreateFields" in self.js

    def test_format_error_still_exists(self) -> None:
        """formatError must still exist (used by both create and edit form submission)."""
        assert "function formatError" in self.js

    def test_escape_html_still_exists(self) -> None:
        """escapeHtml must still exist for XSS prevention."""
        assert "function escapeHtml" in self.js

    def test_dom_content_loaded_handler_exists(self) -> None:
        """DOMContentLoaded handler must still exist."""
        assert "DOMContentLoaded" in self.js

    def test_all_three_page_inits_in_handler(self) -> None:
        """DOMContentLoaded must still dispatch to all 3 page init functions."""
        handler_body = _extract_dcl_handler_body(self.js)

        assert "initTablePage" in handler_body, "DOMContentLoaded must call initTablePage"
        assert "initEditPage" in handler_body, "DOMContentLoaded must call initEditPage"
        assert "initCreatePage" in handler_body, "DOMContentLoaded must call initCreatePage"
