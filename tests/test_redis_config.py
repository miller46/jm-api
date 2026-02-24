"""Tests for Redis configuration and client."""

from unittest.mock import MagicMock, patch

import pytest
import redis

from jm_api.core.config import Settings, get_settings
from jm_api.core.redis_client import (
    RedisConnectionError,
    close_redis,
    create_connection_pool,
    create_redis_client,
    get_connection_pool,
    get_redis,
    get_redis_client,
    init_redis,
    is_redis_available,
)


class TestRedisConfiguration:
    """Tests for Redis configuration in Settings."""

    def test_redis_defaults(self):
        """Test Redis configuration defaults."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
        )
        
        assert settings.redis_url is None
        assert settings.redis_port == 6379
        assert settings.redis_password is None
        assert settings.redis_db == 0
        assert settings.redis_connection_pool_size == 10
        assert settings.redis_connection_pool_max == 20
        assert settings.redis_socket_timeout == 5
        assert settings.redis_socket_connect_timeout == 5
        assert settings.redis_retry_on_timeout is True
        assert settings.redis_health_check_interval == 30

    def test_redis_env_vars(self, monkeypatch):
        """Test Redis configuration from environment variables."""
        monkeypatch.setenv("JM_API_REDIS_URL", "redis.example.com")
        monkeypatch.setenv("JM_API_REDIS_PORT", "6380")
        monkeypatch.setenv("JM_API_REDIS_PASSWORD", "secret123")
        monkeypatch.setenv("JM_API_REDIS_DB", "1")
        monkeypatch.setenv("JM_API_REDIS_CONNECTION_POOL_SIZE", "20")
        monkeypatch.setenv("JM_API_REDIS_CONNECTION_POOL_MAX", "50")
        
        # Clear cache to pick up new env vars
        get_settings.cache_clear()
        
        settings = get_settings()
        assert settings.redis_url == "redis.example.com"
        assert settings.redis_port == 6380
        assert settings.redis_password == "secret123"
        assert settings.redis_db == 1
        assert settings.redis_connection_pool_size == 20
        assert settings.redis_connection_pool_max == 50


class TestRedisConnectionPool:
    """Tests for Redis connection pool creation."""

    def test_create_connection_pool_no_url_raises(self):
        """Test that creating pool without URL raises error."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url=None,
        )
        
        with pytest.raises(RedisConnectionError, match="Redis URL not configured"):
            create_connection_pool(settings)

    @patch("jm_api.core.redis_client.ConnectionPool")
    def test_create_connection_pool_with_url(self, mock_pool_class):
        """Test creating connection pool with URL."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
            redis_port=6379,
        )
        
        create_connection_pool(settings)
        
        mock_pool_class.assert_called_once()
        call_kwargs = mock_pool_class.call_args.kwargs
        assert call_kwargs["host"] == "localhost"
        assert call_kwargs["port"] == 6379
        assert call_kwargs["db"] == 0

    @patch("jm_api.core.redis_client.ConnectionPool")
    def test_create_connection_pool_with_password(self, mock_pool_class):
        """Test creating connection pool with password."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
            redis_password="my-password",
        )
        
        create_connection_pool(settings)
        
        call_kwargs = mock_pool_class.call_args.kwargs
        assert call_kwargs["password"] == "my-password"


class TestRedisClient:
    """Tests for Redis client creation."""

    def test_create_redis_client_no_url_raises(self):
        """Test that creating client without URL raises error."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url=None,
        )
        
        with pytest.raises(RedisConnectionError, match="Redis URL not configured"):
            create_redis_client(settings)

    @patch("jm_api.core.redis_client.redis.Redis")
    @patch("jm_api.core.redis_client.get_connection_pool")
    def test_create_redis_client(self, mock_get_pool, mock_redis_class):
        """Test creating Redis client."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
        )
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        
        create_redis_client(settings)
        
        mock_redis_class.assert_called_once()
        call_kwargs = mock_redis_class.call_args.kwargs
        assert call_kwargs["connection_pool"] == mock_pool


class TestInitRedis:
    """Tests for Redis initialization."""

    @patch("jm_api.core.redis_client.get_settings")
    def test_init_redis_skipped_when_no_url(self, mock_get_settings, caplog):
        """Test that init_redis skips when URL not configured."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url=None,
        )
        mock_get_settings.return_value = settings
        
        result = init_redis()
        
        assert result is None

    @patch("jm_api.core.redis_client.redis.Redis")
    @patch("jm_api.core.redis_client.create_connection_pool")
    def test_init_redis_success(self, mock_create_pool, mock_redis_class):
        """Test successful Redis initialization."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
        )
        
        mock_pool = MagicMock()
        mock_create_pool.return_value = mock_pool
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client
        
        with patch("jm_api.core.redis_client.get_settings") as mock_get_settings:
            mock_get_settings.return_value = settings
            result = init_redis()
        
        assert result == mock_client
        mock_client.ping.assert_called_once()

    @patch("jm_api.core.redis_client.create_connection_pool")
    def test_init_redis_connection_error(self, mock_create_pool):
        """Test Redis initialization with connection error."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
        )
        
        mock_create_pool.side_effect = redis.ConnectionError("Connection refused")
        
        with patch("jm_api.core.redis_client.get_settings") as mock_get_settings:
            mock_get_settings.return_value = settings
            with pytest.raises(RedisConnectionError, match="Failed to connect to Redis"):
                init_redis()

    @patch("jm_api.core.redis_client.redis.Redis")
    @patch("jm_api.core.redis_client.create_connection_pool")
    def test_init_redis_stores_in_app_state(self, mock_create_pool, mock_redis_class):
        """Test that init_redis stores client in app state."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
        )
        
        mock_pool = MagicMock()
        mock_create_pool.return_value = mock_pool
        mock_client = MagicMock()
        mock_redis_class.return_value = mock_client
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        
        with patch("jm_api.core.redis_client.get_settings") as mock_get_settings:
            mock_get_settings.return_value = settings
            init_redis(mock_app)
        
        assert mock_app.state.redis == mock_client
        assert mock_app.state.redis_pool == mock_pool


class TestRedisHelpers:
    """Tests for Redis helper functions."""

    def test_get_redis_client_returns_none_when_not_initialized(self):
        """Test get_redis_client returns None when not initialized."""
        with patch("jm_api.core.redis_client._redis_client", None):
            result = get_redis_client()
            assert result is None

    def test_get_redis_raises_when_not_initialized(self):
        """Test get_redis raises when not initialized."""
        with patch("jm_api.core.redis_client._redis_client", None):
            with pytest.raises(RedisConnectionError, match="Redis client not initialized"):
                get_redis()

    def test_get_redis_returns_client_when_initialized(self):
        """Test get_redis returns client when initialized."""
        mock_client = MagicMock()
        with patch("jm_api.core.redis_client._redis_client", mock_client):
            result = get_redis()
            assert result == mock_client

    def test_is_redis_available_false_when_not_initialized(self):
        """Test is_redis_available returns False when not initialized."""
        with patch("jm_api.core.redis_client._redis_client", None):
            assert is_redis_available() is False

    def test_is_redis_available_true_when_initialized(self):
        """Test is_redis_available returns True when initialized and ping succeeds."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("jm_api.core.redis_client._redis_client", mock_client):
            assert is_redis_available() is True

    def test_is_redis_available_false_when_ping_fails(self):
        """Test is_redis_available returns False when ping fails."""
        mock_client = MagicMock()
        mock_client.ping.side_effect = redis.ConnectionError("Connection lost")
        with patch("jm_api.core.redis_client._redis_client", mock_client):
            assert is_redis_available() is False


class TestCloseRedis:
    """Tests for closing Redis connections."""

    def test_close_redis_no_pool_does_nothing(self):
        """Test close_redis does nothing when no pool exists."""
        with patch("jm_api.core.redis_client._connection_pool", None):
            close_redis()  # Should not raise

    def test_close_redis_disconnects_pool(self):
        """Test close_redis disconnects the pool."""
        mock_pool = MagicMock()
        with patch("jm_api.core.redis_client._connection_pool", mock_pool):
            with patch("jm_api.core.redis_client._redis_client", MagicMock()):
                close_redis()
        
        mock_pool.disconnect.assert_called_once()

    def test_close_redis_handles_disconnect_error(self):
        """Test close_redis handles disconnect errors gracefully."""
        mock_pool = MagicMock()
        mock_pool.disconnect.side_effect = Exception("Disconnect error")
        
        with patch("jm_api.core.redis_client._connection_pool", mock_pool):
            with patch("jm_api.core.redis_client._redis_client", MagicMock()):
                close_redis()  # Should not raise


class TestGetConnectionPool:
    """Tests for get_connection_pool function."""

    def test_get_connection_pool_creates_new_pool(self):
        """Test get_connection_pool creates a new pool when none exists."""
        settings = Settings(
            database_url="sqlite:///:memory:",
            jwt_secret_key="test-secret-key-32-bytes-long-for-testing",
            redis_url="localhost",
        )
        
        with patch("jm_api.core.redis_client._connection_pool", None):
            with patch("jm_api.core.redis_client.ConnectionPool") as mock_pool_class:
                mock_pool = MagicMock()
                mock_pool_class.return_value = mock_pool
                
                result = get_connection_pool(settings)
                
                assert result == mock_pool
                mock_pool_class.assert_called_once()

    def test_get_connection_pool_returns_existing_pool(self):
        """Test get_connection_pool returns existing pool."""
        mock_pool = MagicMock()
        
        with patch("jm_api.core.redis_client._connection_pool", mock_pool):
            result = get_connection_pool()
            
            assert result == mock_pool
