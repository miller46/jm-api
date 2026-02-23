"""Tests for graceful shutdown functionality."""

from __future__ import annotations

import signal
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jm_api.app import create_app
from jm_api.core import shutdown
from jm_api.core.shutdown import (
    _reset_state_for_tests,
    decrement_active_requests,
    dispose_database_connections,
    drain_connections,
    get_active_request_count,
    graceful_shutdown,
    increment_active_requests,
    is_shutting_down,
    register_signal_handlers,
)


@pytest.fixture(autouse=True)
def reset_shutdown_state():
    """Reset global shutdown state - use as fixture or call directly."""
    _reset_state_for_tests()
    yield
    _reset_state_for_tests()


class TestShutdownState:
    """Tests for shutdown state management."""

    def test_is_shutting_down_initial_state(self) -> None:
        """Test that initial shutdown state is False."""
        assert is_shutting_down() is False

    def test_is_shutting_down_after_event_set(self) -> None:
        """Test that shutdown state is True after event is set."""
        from jm_api.core.shutdown import _signal_handler
        _signal_handler(signal.SIGTERM, None)
        assert is_shutting_down() is True


class TestActiveRequestTracking:
    """Tests for active request counting."""

    def test_get_active_request_count_initial(self) -> None:
        """Test that initial active request count is 0."""
        assert get_active_request_count() == 0

    def test_increment_active_requests(self) -> None:
        """Test incrementing active request count."""
        increment_active_requests()
        assert get_active_request_count() == 1
        
        increment_active_requests()
        assert get_active_request_count() == 2

    def test_decrement_active_requests(self) -> None:
        """Test decrementing active request count."""
        increment_active_requests()
        increment_active_requests()
        
        decrement_active_requests()
        assert get_active_request_count() == 1
        
        decrement_active_requests()
        assert get_active_request_count() == 0

    def test_decrement_active_requests_does_not_go_negative(self) -> None:
        """Test that decrement does not make count negative."""
        decrement_active_requests()
        decrement_active_requests()
        assert get_active_request_count() == 0


class TestSignalHandlers:
    """Tests for signal handler registration."""

    def test_register_signal_handlers_sets_handlers(self) -> None:
        """Test that signal handlers are registered."""
        with patch('signal.signal') as mock_signal:
            register_signal_handlers()
            
            # Should register SIGTERM and SIGINT
            assert mock_signal.call_count == 2
            
            calls = mock_signal.call_args_list
            signals = [call.args[0] for call in calls]
            
            assert signal.SIGTERM in signals
            assert signal.SIGINT in signals


class TestSignalHandlerBehavior:
    """Tests for signal handler behavior."""

    def test_sigterm_handler_sets_shutdown_event(self) -> None:
        """Test that SIGTERM handler sets shutdown event."""
        from jm_api.core.shutdown import _signal_handler
        
        assert is_shutting_down() is False
        
        # Simulate SIGTERM
        _signal_handler(signal.SIGTERM, None)
        
        assert is_shutting_down() is True

    def test_sigint_handler_sets_shutdown_event(self) -> None:
        """Test that SIGINT handler sets shutdown event."""
        from jm_api.core.shutdown import _signal_handler
        
        assert is_shutting_down() is False
        
        # Simulate SIGINT
        _signal_handler(signal.SIGINT, None)
        
        assert is_shutting_down() is True


class TestDrainConnections:
    """Tests for connection draining functionality."""

    def test_drain_connections_completes_when_no_active(self) -> None:
        """Test that draining completes immediately when no active connections."""
        result = drain_connections(timeout_seconds=1.0)
        assert result is True

    def test_drain_connections_waits_for_active_connections(self) -> None:
        """Test that draining waits for active connections to complete."""
        increment_active_requests()
        
        # Start a thread that will decrement after a short delay
        def decrement_after_delay():
            time.sleep(0.1)
            decrement_active_requests()
        
        thread = threading.Thread(target=decrement_after_delay)
        thread.start()
        
        result = drain_connections(timeout_seconds=2.0)
        
        thread.join()
        assert result is True
        assert get_active_request_count() == 0

    def test_drain_connections_times_out(self) -> None:
        """Test that draining times out when connections don't complete."""
        increment_active_requests()
        
        # Don't decrement - should timeout
        result = drain_connections(timeout_seconds=0.1)
        
        assert result is False
        # Request still active since we didn't decrement
        assert get_active_request_count() == 1


class TestDisposeDatabaseConnections:
    """Tests for database connection disposal."""

    def test_dispose_database_connections_with_engine(self, app: FastAPI) -> None:
        """Test disposing database connections with valid engine."""
        mock_engine = MagicMock()
        app.state.db_engine = mock_engine
        
        dispose_database_connections(app)
        
        mock_engine.dispose.assert_called_once()

    def test_dispose_database_connections_without_engine(self, app: FastAPI) -> None:
        """Test disposing when no engine exists - should not raise."""
        if hasattr(app.state, "db_engine"):
            delattr(app.state, "db_engine")
        
        # Should not raise an exception
        dispose_database_connections(app)

    def test_dispose_database_connections_handles_exception(self, app: FastAPI) -> None:
        """Test that dispose handles exceptions gracefully."""
        mock_engine = MagicMock()
        mock_engine.dispose.side_effect = Exception("Dispose error")
        app.state.db_engine = mock_engine
        
        # Should not raise an exception
        dispose_database_connections(app)


class TestGracefulShutdown:
    """Tests for graceful shutdown function."""

    def test_graceful_shutdown_drains_and_disposes(self, app: FastAPI) -> None:
        """Test that graceful shutdown drains connections and disposes DB."""
        mock_engine = MagicMock()
        app.state.db_engine = mock_engine
        
        graceful_shutdown(app, timeout_seconds=1.0)
        
        mock_engine.dispose.assert_called_once()


class TestGracefulShutdownMiddleware:
    """Tests for the graceful shutdown middleware."""

    def test_request_rejected_when_shutting_down(self, reset_shutdown_state) -> None:
        """Test that new requests are rejected when shutting down."""
        from jm_api.middleware.graceful_shutdown import GracefulShutdownMiddleware
        
        app = FastAPI()
        app.add_middleware(GracefulShutdownMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}
        
        with TestClient(app) as client:
            # First request should work
            response = client.get("/test")
            assert response.status_code == 200
            
            # Set shutdown event
            from jm_api.core.shutdown import _signal_handler
            _signal_handler(signal.SIGTERM, None)
            
            # Request during shutdown should be rejected
            response = client.get("/test")
            assert response.status_code == 503
            assert "Retry-After" in response.headers
            assert response.json()["detail"] == "Service is shutting down. Please retry later."

    def test_active_requests_tracked_correctly(self, reset_shutdown_state) -> None:
        """Test that active requests are tracked during request lifecycle."""
        # Reset state before this test
        from jm_api.core.shutdown import _reset_state_for_tests
        _reset_state_for_tests()
        
        from jm_api.middleware.graceful_shutdown import GracefulShutdownMiddleware
        
        app = FastAPI()
        app.add_middleware(GracefulShutdownMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}
        
        # Before any requests
        assert get_active_request_count() == 0
        
        with TestClient(app) as client:
            # Make a request
            response = client.get("/test")
            assert response.status_code == 200
        
        # After request completes (give a small moment for cleanup)
        import time
        time.sleep(0.1)
        assert get_active_request_count() == 0


class TestIntegrationWithApp:
    """Integration tests for graceful shutdown with the full app."""

    def test_app_starts_with_graceful_shutdown_middleware(self, reset_shutdown_state) -> None:
        """Test that the app starts correctly with graceful shutdown middleware."""
        from jm_api.core.shutdown import _reset_state_for_tests
        _reset_state_for_tests()
        
        app = create_app()
        
        # Check that the middleware is in the stack
        # Middleware cls attribute contains the actual class
        middleware_classes = [
            m.cls.__name__ if hasattr(m, 'cls') else m.__class__.__name__
            for m in app.user_middleware
        ]
        assert "GracefulShutdownMiddleware" in middleware_classes

    def test_health_check_works_during_normal_operation(self, reset_shutdown_state) -> None:
        """Test that health checks work during normal operation."""
        from jm_api.core.shutdown import _reset_state_for_tests
        _reset_state_for_tests()
        
        from jm_api.app import create_app
        app = create_app()
        
        with TestClient(app) as client:
            response = client.get("/api/v1/live")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
