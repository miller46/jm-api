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
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=True,
            )

    def test_database_url_postgresql_allowed_in_production(self) -> None:
        """PostgreSQL database_url works in production."""
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@localhost/proddb",
            jwt_secret_key="x" * 32,
            rate_limit_storage_uri="redis://localhost:6379/0",
            bots_write_admin_only=True,
        )
        assert settings.database_url == "postgresql://user:pass@localhost/proddb"

    def test_database_url_sqlite_not_allowed_in_staging(self) -> None:
        """Staging environment also rejects SQLite database_url."""
        with pytest.raises(ValueError, match="SQLite is not recommended for production"):
            Settings(
                environment="staging",
                database_url="sqlite:///./staging.db",
            )

    def test_default_jwt_secret_not_allowed_in_production(self) -> None:
        """Production environment requires overriding the default JWT secret."""
        with pytest.raises(ValueError, match="Default JWT secret is not allowed"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=True,
            )

    def test_rate_limit_memory_not_allowed_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_RATE_LIMIT_STORAGE_URI cannot be memory://"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                bots_write_admin_only=True,
                rate_limit_storage_uri="memory://",
            )

    def test_bots_write_must_be_admin_only_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_BOTS_WRITE_ADMIN_ONLY must be true"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=False,
            )

    def test_bots_write_exception_flag_allows_temporary_bypass(self) -> None:
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@localhost/proddb",
            jwt_secret_key="x" * 32,
            rate_limit_storage_uri="redis://localhost:6379/0",
            bots_write_admin_only=False,
            i_understand_risk=True,
        )
        assert settings.i_understand_risk is True

    def test_trust_proxy_headers_requires_cidrs_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_TRUST_PROXY_HEADERS=true requires"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=True,
                trust_proxy_headers=True,
            )

    def test_trust_proxy_headers_with_cidrs_in_production(self) -> None:
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@localhost/proddb",
            jwt_secret_key="x" * 32,
            rate_limit_storage_uri="redis://localhost:6379/0",
            bots_write_admin_only=True,
            trust_proxy_headers=True,
            trusted_proxy_cidrs="10.0.0.0/8,172.16.0.0/12",
        )
        assert settings.trusted_proxy_cidrs == ["10.0.0.0/8", "172.16.0.0/12"]

    def test_short_jwt_secret_not_allowed_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_JWT_SECRET_KEY must be at least 32 bytes"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="short-key",
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=True,
            )

    def test_non_production_can_bypass_production_invariants(self) -> None:
        settings = Settings(
            environment="development",
            database_url="sqlite:///./dev.db",
            jwt_secret_key="short-key",
            rate_limit_storage_uri="memory://",
            bots_write_admin_only=False,
            trust_proxy_headers=True,
        )
        assert settings.environment == "development"


class TestProductionSecurityInvariants:
    """Production/staging fail-fast invariant checks."""

    def test_rate_limit_storage_memory_not_allowed_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_RATE_LIMIT_STORAGE_URI cannot be memory://"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="memory://",
            )

    def test_bots_write_admin_only_required_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_BOTS_WRITE_ADMIN_ONLY must be true"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="redis://localhost:6379/0",
                bots_write_admin_only=False,
            )

    def test_bots_write_admin_only_allows_explicit_risk_acknowledgement(self) -> None:
        settings = Settings(
            environment="production",
            database_url="postgresql://user:pass@localhost/proddb",
            jwt_secret_key="x" * 32,
            rate_limit_storage_uri="redis://localhost:6379/0",
            bots_write_admin_only=False,
            i_understand_risk=True,
        )
        assert settings.i_understand_risk is True

    def test_trust_proxy_headers_requires_trusted_proxy_cidrs(self) -> None:
        with pytest.raises(ValueError, match="JM_API_TRUST_PROXY_HEADERS=true requires"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                rate_limit_storage_uri="redis://localhost:6379/0",
                trust_proxy_headers=True,
            )

    def test_invalid_trusted_proxy_cidrs_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid proxy CIDR"):
            Settings(
                environment="development",
                database_url="sqlite:///:memory:",
                trusted_proxy_cidrs=["not-a-cidr"],
            )

    def test_jwt_secret_must_be_32_bytes_in_production(self) -> None:
        with pytest.raises(ValueError, match="JM_API_JWT_SECRET_KEY must be at least 32 bytes"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="short-secret",
                rate_limit_storage_uri="redis://localhost:6379/0",
            )

    def test_jwt_signing_keys_must_be_32_bytes_in_production(self) -> None:
        with pytest.raises(ValueError, match="each JWT signing key in JM_API_JWT_SIGNING_KEYS"):
            Settings(
                environment="production",
                database_url="postgresql://user:pass@localhost/proddb",
                jwt_secret_key="x" * 32,
                jwt_signing_keys=["x" * 32, "too-short"],
                rate_limit_storage_uri="redis://localhost:6379/0",
            )

    def test_non_production_can_use_convenience_defaults(self) -> None:
        settings = Settings(
            environment="development",
            database_url="sqlite:///:memory:",
            jwt_secret_key="short",
            rate_limit_storage_uri="memory://",
            bots_write_admin_only=False,
            trust_proxy_headers=True,
        )
        assert settings.environment == "development"


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

    def test_warn_log_level_normalizes_to_warning(self) -> None:
        settings = Settings(database_url="sqlite:///:memory:", log_level="WARN")
        assert settings.log_level == "WARNING"

    def test_invalid_log_sample_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="log_sample_rate"):
            Settings(database_url="sqlite:///:memory:", log_sample_rate=0)
