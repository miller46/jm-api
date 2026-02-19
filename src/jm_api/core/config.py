from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments that require explicit production safeguards
_PRODUCTION_ENVIRONMENTS = {"production", "staging"}
_DEFAULT_JWT_SECRET = "change-me-in-production-change-me-in-production"


class Settings(BaseSettings):
    app_name: str = Field(default="jm-api")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    # No default - must be explicitly configured via JM_API_DATABASE_URL env var
    database_url: str = Field()

    @model_validator(mode="after")
    def validate_database_url_for_environment(self) -> "Settings":
        """Validate database_url is appropriate for the environment."""
        if self.environment in _PRODUCTION_ENVIRONMENTS:
            # Check if using any SQLite database (not suitable for production)
            if self.database_url.startswith("sqlite"):
                raise ValueError(
                    "SQLite is not recommended for production. "
                    "Use PostgreSQL or another production database."
                )

            if self.jwt_secret_key == _DEFAULT_JWT_SECRET:
                raise ValueError(
                    "Default JWT secret is not allowed in production/staging. "
                    "Set JM_API_JWT_SECRET_KEY to a strong secret."
                )
        return self

    api_v1_prefix: str = Field(default="/api/v1")

    docs_enabled: bool = Field(default=True)
    openapi_url: str = Field(default="/openapi.json")
    docs_url: str = Field(default="/docs")
    redoc_url: str = Field(default="/redoc")

    request_id_header: str = Field(default="X-Request-ID")

    allow_origins: list[str] = Field(default_factory=list)
    cors_allow_credentials: bool = Field(default=True)
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    allowed_hosts: list[str] = Field(default_factory=list)

    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=True)
    log_sample_rate: float = Field(default=1.0)
    slow_query_threshold_ms: int = Field(default=500)

    tracing_enabled: bool = Field(default=False)
    tracing_service_name: str = Field(default="jm-api")
    tracing_service_version: str = Field(default="0.1.0")
    tracing_jaeger_host: str = Field(default="localhost")
    tracing_jaeger_port: int = Field(default=6831)

    metrics_enabled: bool = Field(default=True)
    metrics_path: str = Field(default="/metrics")

    # JWT Settings
    jwt_secret_key: str = Field(default=_DEFAULT_JWT_SECRET)
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=15)
    jwt_refresh_token_expire_days: int = Field(default=7)
    session_cleanup_interval_seconds: int = Field(default=300)

    model_config = SettingsConfigDict(
        env_prefix="JM_API_",
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("allow_origins", "allowed_hosts", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> list[str] | object:
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if normalized == "WARN":
            return "WARNING"
        return normalized

    @field_validator("log_sample_rate")
    @classmethod
    def validate_sample_rate(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("log_sample_rate must be > 0 and <= 1")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
