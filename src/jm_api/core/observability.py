from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import FastAPI, Response
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import Engine, event
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from jm_api.core.config import Settings

logger = structlog.get_logger(__name__)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "version", "method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "version", "method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total HTTP errors",
    ["service", "version", "method", "endpoint", "status"],
)


class MetricsMiddleware:
    """Collect request metrics with bounded-label cardinality."""

    def __init__(self, app: ASGIApp, service: str, version: str) -> None:
        self.app = app
        self.service = service
        self.version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        endpoint = self._metric_endpoint(scope)
        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self._record_metrics(method=method, endpoint=endpoint, status_code=500, start=start)
            raise

        self._record_metrics(method=method, endpoint=endpoint, status_code=status_code, start=start)

    def _metric_endpoint(self, scope: Scope) -> str:
        """Prefer route template to avoid high-cardinality labels (e.g., IDs in paths)."""
        route = scope.get("route")
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and route_path:
            return route_path
        path = scope.get("path", "")
        return str(path) if path else "unknown"

    def _record_metrics(self, method: str, endpoint: str, status_code: int, start: float) -> None:
        duration = time.perf_counter() - start
        status_label = str(status_code)
        REQUEST_COUNT.labels(self.service, self.version, method, endpoint, status_label).inc()
        REQUEST_LATENCY.labels(self.service, self.version, method, endpoint).observe(duration)
        if status_code >= 400:
            REQUEST_ERRORS.labels(self.service, self.version, method, endpoint, status_label).inc()


def install_metrics(app: FastAPI, settings: Settings) -> None:
    """Install Prometheus metrics endpoint and middleware."""
    if not settings.metrics_enabled:
        return

    app.add_middleware(
        MetricsMiddleware,
        service=settings.app_name,
        version=settings.app_version,
    )

    @app.get(settings.metrics_path, include_in_schema=False)
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def install_tracing(app: FastAPI, settings: Settings) -> None:
    """Install tracing instrumentation in an idempotent way."""
    if not settings.tracing_enabled:
        return

    if getattr(app.state, "tracing_installed", False):
        return

    resource = Resource.create(
        {
            "service.name": settings.tracing_service_name,
            "service.version": settings.tracing_service_version,
            "deployment.environment": settings.environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    jaeger_exporter = JaegerExporter(
        agent_host_name=settings.tracing_jaeger_host,
        agent_port=settings.tracing_jaeger_port,
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

    current_provider: Any = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        trace.set_tracer_provider(tracer_provider)
        current_provider = tracer_provider

    FastAPIInstrumentor.instrument_app(app, tracer_provider=current_provider)
    app.state.tracing_installed = True


def instrument_sqlalchemy(engine: Engine, settings: Settings) -> None:
    """Instrument SQLAlchemy and emit structured query timing logs."""
    if settings.tracing_enabled:
        SQLAlchemyInstrumentor().instrument(engine=engine)

    threshold_ms = settings.slow_query_threshold_ms

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(_conn, cursor, statement, parameters, context, executemany):
        del cursor, parameters, executemany
        context._query_start_time = time.perf_counter()
        logger.debug("db.query.start", statement=statement)

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(_conn, cursor, statement, parameters, context, executemany):
        del cursor, parameters, executemany
        elapsed_ms = (time.perf_counter() - context._query_start_time) * 1000
        level = "warning" if elapsed_ms >= threshold_ms else "debug"
        getattr(logger, level)(
            "db.query.complete",
            statement=statement,
            duration_ms=round(elapsed_ms, 2),
            slow_query=elapsed_ms >= threshold_ms,
        )
