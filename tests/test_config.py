"""Tests for application configuration."""

import pytest
from pydantic import ValidationError

from jm_api.core.config import Settings


class TestDatabaseUrlConfig:
    """Test database_url configuration behavior."""

    def test_database_url_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_url must be explicitly configured."""
        # Remove env var to test that it's required
        monkeypatch.delenv("JM_API_DATABASE_URL", raising=False)
        with pytest.raises(ValidationError, match="database_url"):
            Settings(environment="development")

    def test_database_url_sqlite_allowed_in_development(self) -> None:
        """SQLite database_url is allowed in development environment."""
        settings = Settings(
            environment="development",
            database_url="sqlite:///./dev.db",
        )
        assert settings.database_url == "sqlite:///./dev.db"

    def test_database_url_custom_value_in_development(self) -> None:
        """Custom database_url works in development."""
        settings = Settings(
            environment="development",
            database_url="postgresql://localhost/mydb",
        )
        assert settings.database_url == "postgresql://localhost/mydb"

    def test_database_url_sqlite_not_allowed_in_production(self) -> None:
        """SQLite is not allowed in production environment."""
        with pytest.raises(ValueError, match="SQLite is not recommended for production"):
            Settings(
                environment="production",
                database_url="sqlite:///./app.db",
            )

    def test_database_url_postgresql_allowed_in_production(self) -> None:
        """PostgreSQL database_url works in production."""
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@localhost/proddb",
        )
        assert settings.database_url == "postgresql://user:pass@localhost/proddb"

    def test_database_url_sqlite_not_allowed_in_staging(self) -> None:
        """Staging environment also rejects SQLite database_url."""
        with pytest.raises(ValueError, match="SQLite is not recommended for production"):
            Settings(
                environment="staging",
                database_url="sqlite:///./staging.db",
            )


class TestEnvironmentDefaults:
    """Test environment-related defaults."""

    def test_default_environment_is_development(self) -> None:
        """Default environment is development."""
        settings = Settings(database_url="sqlite:///:memory:")
        assert settings.environment == "development"

    def test_debug_default_is_false(self) -> None:
        """Debug defaults to False."""
        settings = Settings(database_url="sqlite:///:memory:")
        assert settings.debug is False
