from __future__ import annotations

from functools import lru_cache
from ipaddress import ip_network

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
    db_migration_check_enabled: bool = Field(default=True)

    api_v1_prefix: str = Field(default="/api/v1")

    docs_enabled: bool = Field(default=True)
    openapi_url: str = Field(default="/openapi.json")
    docs_url: str = Field(default="/docs")
    redoc_url: str = Field(default="/redoc")

    request_id_header: str = Field(default="X-Request-ID")

    security_headers_enabled: bool = Field(default=True)
    security_header_x_content_type_options: str = Field(default="nosniff")
    security_header_x_frame_options: str = Field(default="DENY")
    security_header_hsts_max_age: int = Field(default=31536000)
    security_header_hsts_include_subdomains: bool = Field(default=True)
    security_header_hsts_preload: bool = Field(default=False)
    security_header_admin_csp: str = Field(
        default="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self';"
    )

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

    # Deployment metadata
    git_sha: str | None = Field(default=None)
    deployed_at: str | None = Field(default=None)

    # JWT Settings
    jwt_secret_key: str = Field(default=_DEFAULT_JWT_SECRET)
    jwt_signing_keys: list[str] = Field(default_factory=list)
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=15)
    jwt_refresh_token_expire_days: int = Field(default=7)
    session_cleanup_interval_seconds: int = Field(default=300)
    session_cleanup_grace_days: int = Field(default=7)
    trust_proxy_headers: bool = Field(default=False)
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    bots_write_admin_only: bool = Field(default=False)
    i_understand_risk: bool = Field(default=False)

    # API-wide and per-user rate limiting / quotas
    rate_limit_storage_uri: str = Field(default="memory://")
    rate_limit_api_per_minute: int = Field(default=120)
    rate_limit_api_per_hour: int = Field(default=3000)
    rate_limit_quota_per_day: int = Field(default=10000)
    rate_limit_quota_per_month: int = Field(default=200000)

    # Redis configuration (Heroku environment variables)
    redis_url: str | None = Field(default=None)
    redis_port: int = Field(default=6379)
    redis_password: str | None = Field(default=None)
    redis_db: int = Field(default=0)
    redis_connection_pool_size: int = Field(default=10)
    redis_connection_pool_max: int = Field(default=20)
    redis_socket_timeout: int = Field(default=5)
    redis_socket_connect_timeout: int = Field(default=5)
    redis_retry_on_timeout: bool = Field(default=True)
    redis_health_check_interval: int = Field(default=30)

    model_config = SettingsConfigDict(
        env_prefix="JM_API_",
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("allow_origins", "allowed_hosts", "jwt_signing_keys", "trusted_proxy_cidrs", mode="before")
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

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: list[str]) -> list[str]:
        for cidr in value:
            try:
                ip_network(cidr, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid proxy CIDR: {cidr}") from exc
        return value

    @model_validator(mode="after")
    def validate_database_url_for_environment(self) -> "Settings":
        """Validate production/staging deployment invariants."""
        if self.environment not in _PRODUCTION_ENVIRONMENTS:
            return self

        errors: list[str] = []

        if self.database_url.startswith("sqlite"):
            errors.append(
                "Production config error: SQLite is not recommended for production. "
                "Use PostgreSQL or another production database."
            )

        if self.jwt_secret_key == _DEFAULT_JWT_SECRET and not self.jwt_signing_keys:
            errors.append(
                "Production config error: Default JWT secret is not allowed in "
                "production/staging. Set JM_API_JWT_SECRET_KEY to a strong secret."
            )

        if self.rate_limit_storage_uri.strip().lower() == "memory://":
            errors.append(
                "Production config error: JM_API_RATE_LIMIT_STORAGE_URI cannot be memory:// "
                "— use Redis for distributed rate limiting."
            )

        if not self.bots_write_admin_only and not self.i_understand_risk:
            errors.append(
                "Production config error: JM_API_BOTS_WRITE_ADMIN_ONLY must be true. "
                "If you need a temporary exception, set JM_API_I_UNDERSTAND_RISK=true explicitly."
            )

        if self.trust_proxy_headers and not self.trusted_proxy_cidrs:
            errors.append(
                "Production config error: JM_API_TRUST_PROXY_HEADERS=true requires "
                "JM_API_TRUSTED_PROXY_CIDRS to be configured (comma-separated CIDRs)."
            )

        effective_keys = [key for key in self.jwt_signing_keys if key] or [self.jwt_secret_key]
        for index, key in enumerate(effective_keys, start=1):
            if len(key.encode("utf-8")) < 32:
                if self.jwt_signing_keys:
                    errors.append(
                        "Production config error: each JWT signing key in JM_API_JWT_SIGNING_KEYS "
                        f"must be at least 32 bytes (key #{index} is too short)."
                    )
                else:
                    errors.append(
                        "Production config error: JM_API_JWT_SECRET_KEY must be at least 32 bytes."
                    )

        if errors:
            raise ValueError("\n".join(errors))

        return self

    @property
    def security_header_hsts_value(self) -> str:
        value = f"max-age={self.security_header_hsts_max_age}"
        if self.security_header_hsts_include_subdomains:
            value += "; includeSubDomains"
        if self.security_header_hsts_preload:
            value += "; preload"
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
