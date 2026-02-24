from __future__ import annotations

from typing import TYPE_CHECKING

import redis
import structlog
from redis.connection import ConnectionPool

if TYPE_CHECKING:
    from fastapi import FastAPI

from jm_api.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Global Redis client instance
_redis_client: redis.Redis | None = None
_connection_pool: ConnectionPool | None = None


class RedisConnectionError(Exception):
    """Raised when Redis connection fails."""

    pass


def create_connection_pool(settings: Settings | None = None) -> ConnectionPool:
    """Create a Redis connection pool from settings.

    Args:
        settings: Application settings. If None, uses cached settings.

    Returns:
        Configured Redis connection pool.

    Raises:
        RedisConnectionError: If Redis URL is not configured.
    """
    if settings is None:
        settings = get_settings()

    if not settings.redis_url:
        raise RedisConnectionError(
            "Redis URL not configured. Set JM_API_REDIS_URL environment variable."
        )

    connection_kwargs = {
        "host": settings.redis_url,
        "port": settings.redis_port,
        "db": settings.redis_db,
        "socket_timeout": settings.redis_socket_timeout,
        "socket_connect_timeout": settings.redis_socket_connect_timeout,
        "retry_on_timeout": settings.redis_retry_on_timeout,
        "health_check_interval": settings.redis_health_check_interval,
        "max_connections": settings.redis_connection_pool_max,
    }

    if settings.redis_password:
        connection_kwargs["password"] = settings.redis_password

    logger.info(
        "redis.creating_pool",
        host=settings.redis_url,
        port=settings.redis_port,
        db=settings.redis_db,
        pool_size=settings.redis_connection_pool_size,
    )

    return ConnectionPool(**connection_kwargs)


def get_connection_pool(settings: Settings | None = None) -> ConnectionPool:
    """Get or create the global Redis connection pool.

    Args:
        settings: Application settings. If None, uses cached settings.

    Returns:
        The global connection pool, creating it if necessary.
    """
    global _connection_pool

    if _connection_pool is None:
        _connection_pool = create_connection_pool(settings)

    return _connection_pool


def create_redis_client(
    settings: Settings | None = None,
    connection_pool: ConnectionPool | None = None,
) -> redis.Redis:
    """Create a Redis client from settings.

    Args:
        settings: Application settings. If None, uses cached settings.
        connection_pool: Optional connection pool to use. If None, creates one.

    Returns:
        Configured Redis client.

    Raises:
        RedisConnectionError: If Redis URL is not configured.
    """
    if settings is None:
        settings = get_settings()

    if not settings.redis_url:
        raise RedisConnectionError(
            "Redis URL not configured. Set JM_API_REDIS_URL environment variable."
        )

    if connection_pool is None:
        connection_pool = get_connection_pool(settings)

    client = redis.Redis(
        connection_pool=connection_pool,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        retry_on_timeout=settings.redis_retry_on_timeout,
        health_check_interval=settings.redis_health_check_interval,
    )

    return client


def init_redis(app: FastAPI | None = None) -> redis.Redis | None:
    """Initialize the global Redis client.

    This function creates the Redis connection pool and client,
    storing them in global variables and optionally in app state.

    Args:
        app: Optional FastAPI app to store the client in app.state.

    Returns:
        The initialized Redis client, or None if Redis is not configured.

    Raises:
        RedisConnectionError: If connection fails and Redis is required.
    """
    global _redis_client, _connection_pool

    settings = get_settings()

    # Skip initialization if Redis URL is not configured
    if not settings.redis_url:
        logger.info("redis.skipped", reason="JM_API_REDIS_URL not configured")
        return None

    try:
        # Create connection pool
        _connection_pool = create_connection_pool(settings)

        # Create Redis client
        _redis_client = redis.Redis(connection_pool=_connection_pool)

        # Test connection
        _redis_client.ping()

        logger.info(
            "redis.connected",
            host=settings.redis_url,
            port=settings.redis_port,
            db=settings.redis_db,
        )

        # Store in app state if provided
        if app is not None:
            app.state.redis = _redis_client
            app.state.redis_pool = _connection_pool

        return _redis_client

    except redis.ConnectionError as exc:
        logger.error(
            "redis.connection_failed",
            host=settings.redis_url,
            port=settings.redis_port,
            error=str(exc),
        )
        # Clean up partial initialization
        _redis_client = None
        _connection_pool = None
        raise RedisConnectionError(
            f"Failed to connect to Redis at {settings.redis_url}:{settings.redis_port}"
        ) from exc

    except redis.AuthenticationError as exc:
        logger.error(
            "redis.authentication_failed",
            host=settings.redis_url,
            port=settings.redis_port,
        )
        _redis_client = None
        _connection_pool = None
        raise RedisConnectionError("Redis authentication failed") from exc

    except Exception as exc:
        logger.error(
            "redis.initialization_error",
            host=settings.redis_url,
            port=settings.redis_port,
            error=str(exc),
        )
        _redis_client = None
        _connection_pool = None
        raise RedisConnectionError(f"Redis initialization failed: {exc}") from exc


def get_redis_client() -> redis.Redis | None:
    """Get the global Redis client instance.

    Returns:
        The Redis client if initialized, None otherwise.
    """
    return _redis_client


def get_redis() -> redis.Redis:
    """Get the global Redis client, raising if not initialized.

    Returns:
        The Redis client.

    Raises:
        RedisConnectionError: If Redis is not initialized.
    """
    if _redis_client is None:
        raise RedisConnectionError(
            "Redis client not initialized. Call init_redis() first."
        )
    return _redis_client


def close_redis() -> None:
    """Close the Redis connection pool and clean up resources.

    This should be called during application shutdown.
    """
    global _redis_client, _connection_pool

    if _connection_pool is not None:
        try:
            _connection_pool.disconnect()
            logger.info("redis.disconnected")
        except Exception as exc:
            logger.warning("redis.disconnect_error", error=str(exc))
        finally:
            _connection_pool = None
            _redis_client = None


def is_redis_available() -> bool:
    """Check if Redis is configured and available.

    Returns:
        True if Redis client is initialized and can ping, False otherwise.
    """
    if _redis_client is None:
        return False

    try:
        return _redis_client.ping()
    except Exception:
        return False
