from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Environments that require explicit database configuration
_PRODUCTION_ENVIRONMENTS = {"production", "staging"}


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
