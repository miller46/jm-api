from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="jm-api")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

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
