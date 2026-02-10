"""Tests for README environment variable naming consistency.

Verifies that the README uses the `JM_API_` prefix consistently
for all environment variable references, matching the Pydantic Settings
config which uses `env_prefix="JM_API_"`.
"""

import re
from pathlib import Path

README_PATH = Path(__file__).resolve().parent.parent / "README.md"


def _read_readme() -> str:
    return README_PATH.read_text()


def _extract_outside_code_blocks(text: str) -> str:
    """Return README text with fenced code blocks removed."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


class TestQuickstartProseUsesPrefix:
    """Prose below the quickstart code block should reference prefixed env vars."""

    def test_database_url_is_prefixed_in_prose(self):
        """Line 13 prose should say JM_API_DATABASE_URL, not bare DATABASE_URL."""
        readme = _read_readme()
        prose = _extract_outside_code_blocks(readme)

        # Should contain the prefixed version
        assert "JM_API_DATABASE_URL" in prose, (
            "Quickstart prose must reference `JM_API_DATABASE_URL`, not bare `DATABASE_URL`"
        )

    def test_environment_is_prefixed_in_prose(self):
        """Line 14 prose should say JM_API_ENVIRONMENT, not bare ENVIRONMENT."""
        readme = _read_readme()
        prose = _extract_outside_code_blocks(readme)

        # Find lines mentioning ENVIRONMENT in inline code
        env_refs = re.findall(r"`([^`]*ENVIRONMENT[^`]*)`", prose)
        for ref in env_refs:
            assert ref.startswith("JM_API_") or "JM_API_" in ref, (
                f"Found bare `{ref}` — should be prefixed with JM_API_"
            )


class TestConfigTableUsesPrefix:
    """The Configuration table should list env vars with JM_API_ prefix."""

    def test_config_table_database_url_prefixed(self):
        readme = _read_readme()
        # Look for the config table row containing DATABASE_URL
        matches = re.findall(r"\|\s*`([\w_]*DATABASE_URL)`", readme)
        assert matches, "DATABASE_URL should appear in the config table"
        for m in matches:
            assert m.startswith("JM_API_"), (
                f"Config table has `{m}` — should be `JM_API_DATABASE_URL`"
            )

    def test_config_table_environment_prefixed(self):
        readme = _read_readme()
        matches = re.findall(r"\|\s*`([\w_]*ENVIRONMENT)`", readme)
        assert matches, "ENVIRONMENT should appear in the config table"
        for m in matches:
            assert m.startswith("JM_API_"), (
                f"Config table has `{m}` — should be `JM_API_ENVIRONMENT`"
            )

    def test_all_config_table_vars_are_prefixed(self):
        """Every variable in the config table should have the JM_API_ prefix."""
        readme = _read_readme()

        # Extract variable names from the config table (rows starting with | `...`)
        # Skip the header row by looking for backtick-wrapped names
        table_vars = re.findall(r"\|\s*`([\w_]+)`\s*\|", readme)

        # Filter to only known config field names (ignore table header "Variable")
        for var in table_vars:
            if var in ("Variable",):
                continue
            assert var.startswith("JM_API_"), (
                f"Config table entry `{var}` is missing the `JM_API_` prefix"
            )


class TestNoBareEnvVarNamesOutsideCodeBlocks:
    """Ensure no bare (unprefixed) env var names leak into prose."""

    def test_no_bare_database_url_in_prose(self):
        """Outside code blocks, DATABASE_URL references should be prefixed."""
        readme = _read_readme()
        prose = _extract_outside_code_blocks(readme)

        # Find all inline-code references to DATABASE_URL
        refs = re.findall(r"`([^`]*DATABASE_URL[^`]*)`", prose)
        for ref in refs:
            assert "JM_API_" in ref, (
                f"Found bare `{ref}` in prose — should use `JM_API_DATABASE_URL`"
            )
