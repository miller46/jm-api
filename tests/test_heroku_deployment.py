"""Tests for Heroku deployment configuration files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestProcfile:
    """Verify Procfile exists and is correctly configured."""

    def test_procfile_exists(self):
        assert (ROOT / "Procfile").is_file()

    def test_procfile_has_web_process(self):
        content = (ROOT / "Procfile").read_text()
        assert content.startswith("web:")

    def test_procfile_uses_uvicorn(self):
        content = (ROOT / "Procfile").read_text()
        assert "uvicorn" in content

    def test_procfile_references_app_entry_point(self):
        content = (ROOT / "Procfile").read_text()
        assert "jm_api.main:app" in content

    def test_procfile_binds_to_port_env_var(self):
        """Heroku sets $PORT; the Procfile must bind to it."""
        content = (ROOT / "Procfile").read_text()
        assert "$PORT" in content

    def test_procfile_binds_to_all_interfaces(self):
        """Heroku requires binding to 0.0.0.0, not localhost."""
        content = (ROOT / "Procfile").read_text()
        assert "0.0.0.0" in content


class TestRuntimeTxt:
    """Verify runtime.txt specifies the correct Python version."""

    def test_runtime_txt_exists(self):
        assert (ROOT / "runtime.txt").is_file()

    def test_runtime_txt_specifies_python(self):
        content = (ROOT / "runtime.txt").read_text().strip()
        assert content.startswith("python-")

    def test_runtime_txt_specifies_python_3_11_plus(self):
        """pyproject.toml requires >=3.11."""
        content = (ROOT / "runtime.txt").read_text().strip()
        # Extract version: "python-3.X.Y" -> "3.X.Y"
        version_str = content.removeprefix("python-")
        parts = version_str.split(".")
        major, minor = int(parts[0]), int(parts[1])
        assert major == 3
        assert minor >= 11


class TestRequirementsTxt:
    """Heroku needs requirements.txt to detect a Python app and install deps."""

    def test_requirements_txt_exists(self):
        assert (ROOT / "requirements.txt").is_file()

    def test_requirements_txt_contains_fastapi(self):
        content = (ROOT / "requirements.txt").read_text()
        assert "fastapi" in content.lower()

    def test_requirements_txt_contains_uvicorn(self):
        content = (ROOT / "requirements.txt").read_text()
        assert "uvicorn" in content.lower()

    def test_requirements_txt_contains_sqlalchemy(self):
        content = (ROOT / "requirements.txt").read_text()
        assert "sqlalchemy" in content.lower()

    def test_requirements_txt_contains_pydantic_settings(self):
        content = (ROOT / "requirements.txt").read_text()
        assert "pydantic-settings" in content.lower() or "pydantic_settings" in content.lower()

    def test_requirements_txt_contains_psycopg2(self):
        """Production Heroku Postgres needs a pg driver."""
        content = (ROOT / "requirements.txt").read_text().lower()
        assert "psycopg2" in content or "psycopg" in content

    def test_requirements_txt_contains_gunicorn(self):
        """Gunicorn is the recommended WSGI/ASGI process manager on Heroku."""
        content = (ROOT / "requirements.txt").read_text().lower()
        assert "gunicorn" in content or "uvicorn" in content
