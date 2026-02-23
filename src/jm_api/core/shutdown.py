"""Graceful shutdown handling for SIGTERM/SIGINT signals.

Provides signal handlers that drain active connections before exit
and ensure SQLAlchemy connections are explicitly cleaned up.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = structlog.get_logger(__name__)

# Global state for graceful shutdown
_shutdown_event = threading.Event()
_active_requests = 0
_active_requests_lock = threading.Lock()
_shutdown_timeout_seconds = 30  # Match Gunicorn's graceful timeout default


def is_shutting_down() -> bool:
    """Check if the application is currently shutting down."""
    return _shutdown_event.is_set()


def get_active_request_count() -> int:
    """Get the current number of active requests."""
    with _active_requests_lock:
        return _active_requests


def increment_active_requests() -> None:
    """Increment the active request counter."""
    global _active_requests
    with _active_requests_lock:
        _active_requests += 1


def decrement_active_requests() -> None:
    """Decrement the active request counter."""
    global _active_requests
    with _active_requests_lock:
        _active_requests = max(0, _active_requests - 1)


def _signal_handler(signum: int, frame) -> None:
    """Handle SIGTERM/SIGINT signals for graceful shutdown.
    
    Sets the shutdown event to signal that the application should
    stop accepting new requests and begin draining active connections.
    """
    signal_name = signal.Signals(signum).name
    logger.info(
        "shutdown.signal_received",
        signal=signal_name,
        signum=signum,
        active_requests=get_active_request_count(),
    )
    _shutdown_event.set()


def register_signal_handlers() -> None:
    """Register signal handlers for graceful shutdown.
    
    Handles:
    - SIGTERM: Standard termination signal (Docker, Kubernetes, systemd)
    - SIGINT: Interrupt signal (Ctrl+C during development)
    
    Note: Signal handlers can only be registered in the main thread.
    In test environments or worker threads, this will log a warning
    and continue without registering handlers.
    """
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        logger.debug("shutdown.signal_handlers_registered")
    except ValueError as e:
        # Signal handlers can only be registered in the main thread
        # This happens in test environments with TestClient
        logger.warning(
            "shutdown.signal_handlers_skipped",
            reason="not_in_main_thread",
            error=str(e),
        )


def drain_connections(timeout_seconds: float | None = None) -> bool:
    """Wait for active connections to complete.
    
    Args:
        timeout_seconds: Maximum time to wait for connections to drain.
            Defaults to _shutdown_timeout_seconds.
    
    Returns:
        True if all connections drained, False if timeout was reached.
    """
    if timeout_seconds is None:
        timeout_seconds = _shutdown_timeout_seconds
    
    start_time = time.time()
    
    while get_active_request_count() > 0:
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            logger.warning(
                "shutdown.drain_timeout",
                active_requests=get_active_request_count(),
                timeout_seconds=timeout_seconds,
            )
            return False
        
        logger.info(
            "shutdown.draining_connections",
            active_requests=get_active_request_count(),
            elapsed_seconds=elapsed,
        )
        time.sleep(0.5)
    
    logger.info("shutdown.connections_drained", elapsed_seconds=time.time() - start_time)
    return True


def dispose_database_connections(app: FastAPI) -> None:
    """Explicitly dispose of SQLAlchemy database connections.
    
    This ensures all connections in the pool are properly closed,
    preventing connection leaks during shutdown.
    """
    if hasattr(app.state, "db_engine"):
        engine = app.state.db_engine
        logger.info("shutdown.disposing_database_connections")
        try:
            engine.dispose()
            logger.info("shutdown.database_connections_disposed")
        except Exception as e:
            logger.error("shutdown.database_dispose_error", error=str(e))


def graceful_shutdown(app: FastAPI, timeout_seconds: float | None = None) -> None:
    """Perform graceful shutdown of the application.
    
    Steps:
    1. Signal that shutdown is in progress (blocks new requests via middleware)
    2. Wait for active connections to drain
    3. Dispose of SQLAlchemy database connections
    
    Args:
        app: The FastAPI application instance
        timeout_seconds: Maximum time to wait for connections to drain
    """
    logger.info("shutdown.graceful_shutdown_starting")
    
    # Step 1: Drain active connections
    drain_connections(timeout_seconds)
    
    # Step 2: Dispose database connections
    dispose_database_connections(app)
    
    logger.info("shutdown.graceful_shutdown_complete")


def force_exit(code: int = 0) -> None:
    """Force immediate exit of the process.
    
    Used when graceful shutdown cannot complete within the timeout.
    """
    logger.warning("shutdown.force_exit", exit_code=code)
    sys.exit(code)


# Test helpers - only use in tests!
def _reset_state_for_tests() -> None:
    """Reset global state for testing. Do not use in production code."""
    global _active_requests
    _shutdown_event.clear()
    with _active_requests_lock:
        _active_requests = 0
